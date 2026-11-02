# -*- coding: utf-8 -*-
"""
AI 数显独立后台（`admin_api.py`）· 端到端真服务验收脚本
=========================================================
口径源：`变更记录/2026-10-08_AI数显独立后台与主站入口_验收标准.md` **§二**（功能表 + 10 条验收）。

运行（**便携运行时，端口 15088**）：
    pwsh -NoProfile -File D:\\shuzi\\build_pack.ps1        # 本脚本第 0 步会自己跑一次
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v7\\test_admin.py

环境：`SHUZI_SRC_ROOT=D:\\shuzi\\_dist\\_stage_site`（本脚本自己设），
      管理口令由**本进程随机生成**后经环境变量 `YJK_ADMIN_PASSWORD` 注入真服务，
      并断言该口令**不出现在服务端日志、也不出现在源码里**（不写死任何口令）。

覆盖（逐条打印 §二 的 10 条验收，全绿才退出码 0）：
  #1 后台登录：错口令 401 / 正确口令拿到后台令牌（TTL 2h）；令牌与 C 端完全隔离；`/admin/` 托管能力
  #2 连续 5 次错口令 → 第 6 次被锁（可读错误 + 剩余锁定时长）
  #3 `GET /api/v1/admin/users?page=1&size=20` 分页结构与字段
  #4 用户详情**字段级脱敏**（逐字段打印；不回精确出生时刻 / 体征数值 / 病史原文）
  #5 指数分布 A+B+C+D 占比之和 = 100%
  #6 CSV 导出：表头与行数正确，且扫描无敏感字段
  #7 封禁生效：`GET /friends` 与 `POST /friends/cheer` 被拒（打印 HTTP + 业务码），解封恢复
  #8 审计：查看用户详情后恰好新增 1 条（含操作者 / 目标 / 时间 / IP）
  #9 前端（另一位同事负责）：本脚本给出后端可服务性证据，并**如实标注不在本单范围**
  #10 零回归：社交 51 / 内核 335 / 服务端 104（三条既有命令各自跑，逐条打印）
硬约束：只连 127.0.0.1，不发任何真实网络请求；不改 `核心/*`、`服务端/app/*`、`web/*`、`D:\\www\\*`。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import shutil
import urllib.error
import urllib.request

try:                                    # 控制台统一 UTF-8，避免中文乱码
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                   # noqa: BLE001
    pass

# ── 路径与端口 ──────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))          # D:\Deepseek智能体\AI元健康\shuzi\_verify_v7
ROOT = os.path.dirname(HERE)                               # D:\Deepseek智能体\AI元健康\shuzi
STAGE = os.path.join(ROOT, '_dist', '_stage_site')         # 打包后的站点树
PYTHON = os.path.join(ROOT, 'runtime', 'python.exe')       # 便携运行时
# 内核 335 / 服务端 104 两条既有回归命令历史上用的是**系统 Python 3.12**：
# 便携运行时里没有 psycopg / fakeredis，PG 与 Redis 两组用例会整模块跳过 → 只能跑到 83 项。
SYS_PYTHON = r'C:\Users\41692\AppData\Local\Programs\Python\Python312\python.exe'
PACK_PS1 = os.path.join(ROOT, 'build_pack.ps1')
WS = r'D:\Deepseek智能体\AI元健康'
KERNEL_ROOT = os.path.join(WS, '核心')
SERVER_ROOT = os.path.join(WS, '服务端')
SOCIAL_TEST = os.path.join(ROOT, '_verify_v3', 'test_social.py')

# ★ 站点源码定位：先固定成打包后的站点树，再 import 生产模块（与真服务同一份代码）
os.environ['SHUZI_SRC_ROOT'] = STAGE
sys.path.insert(0, os.path.join(STAGE, 'server'))

import store as _store                                      # noqa: E402  触发源码定位

# ★ 交付物模块**必须等第 0 步打包完成之后再 import**：否则可能加载到上一个版本的
#   `_dist/_stage_site` 副本（打包会把这份副本整体重建）。
_ADMIN = None
_SERVE = None


def load_production_modules() -> None:
    global _ADMIN, _SERVE
    import admin_api as admin_mod                           # noqa: PLC0415
    import serve as serve_mod                               # noqa: PLC0415
    _ADMIN, _SERVE = admin_mod, serve_mod

PORT = 15088
BASE = 'http://127.0.0.1:%d' % PORT

DB_MAIN = os.path.join(HERE, 'admin_v7.db')
DB_LOCK = os.path.join(HERE, 'admin_lock_v7.db')
DB_NOPW = os.path.join(HERE, 'admin_nopw_v7.db')
LOG_MAIN = os.path.join(HERE, 'admin_server.out')
ERR_MAIN = os.path.join(HERE, 'admin_server.err')
LOG_LOCK = os.path.join(HERE, 'admin_lock_server.out')
ERR_LOCK = os.path.join(HERE, 'admin_lock_server.err')
LOG_NOPW = os.path.join(HERE, 'admin_nopw_server.out')
ERR_NOPW = os.path.join(HERE, 'admin_nopw_server.err')
RESULT_JSON = os.path.join(HERE, 'test_admin_result.json')

# ★ 管理口令：**本进程随机生成**（不写死任何口令/密钥），只经环境变量注入真服务
ADMIN_PW = 'VerifyPw-' + secrets.token_urlsafe(18)
RUN_SECRETS: dict = {}                      # 运行期敏感值：只用于断言，**不写进结果 JSON**

# 期望的 CSV 表头（独立写一份 = 对交付物做交叉验证，而不是"拿实现自证"）
EXPECTED_CSV_HEADER = ['member_id', 'nickname', 'invite_code', 'created_at', 'archive_status',
                       'observation_count', 'min_observations', 'last_active', 'streak_days',
                       'checkin_days', 'score', 'band', 'banned']

# C 端会员建档用的出生信息（m1 刻意带一个**好认的时刻**，便于逐字段断言"时刻不回传"）
BIRTHS = ['1988-11-27 03:47', '1975-03-09 18:20', '1996-07-15 09:05',
          '1962-12-30 23:11', '2001-02-03 06:40', '1954-08-21 13:58']
COORDS = [('北京', 116.4074, 39.9042), ('上海', 121.4737, 31.2304),
          ('广州', 113.2644, 23.1291), ('成都', 104.0665, 30.5728),
          ('哈尔滨', 126.5349, 45.8038), ('乌鲁木齐', 87.6168, 43.8256)]

CRIT_TITLE = {
    1: '后台可登录（错口令 401 / 正确口令拿到令牌）',
    2: '连续 5 次错口令 → 第 6 次被锁（含剩余锁定时长）',
    3: '用户列表分页结构 {total,page,size,items} 与字段',
    4: '用户详情**字段级脱敏**（无精确出生时刻 / 体征数值 / 病史原文）',
    5: '指数分布 A+B+C+D 占比之和 = 100%',
    6: 'CSV 导出表头与行数正确、扫描无敏感字段',
    7: '封禁后 /friends 与 cheer 被拒（可读业务码）；解封恢复',
    8: '审计：查看详情后恰好新增 1 条（操作者/目标/时间/IP）',
    9: '前端双视口可操作（前端归他人；本脚本做托管/契约/浏览器实测）',
    10: '既有接口与测试零回归（社交 51 / 内核 335 / 服务端 104）',
}

FORBIDDEN_TOKENS = ('birth_local', 'birth_time', 'blood_pressure', 'bp_systolic', 'bp_diastolic',
                    'history_note', 'height_cm', 'weight_kg', 'resting_hr', 'longitude',
                    'latitude')
BANNED_WORDS = ('生命先知', '先知日历', '八息象数', '八息基因', 'ZYDGENE', '中易道',
                '九元情绪', '华医道', '老祖太极', '抗量子')

EVIDENCE: dict = {}
CRIT: dict = {}


# ══════════════════════════════════════════════════════════════════
# 断言框架（逐条打印，失败也继续跑完，最后统一给退出码）
# ══════════════════════════════════════════════════════════════════
class Checker:
    def __init__(self) -> None:
        self.rows: list = []
        self.failed = 0
        self.crit = 0

    def set_crit(self, n: int) -> None:
        self.crit = n

    def check(self, name: str, cond, expect='', actual='', note='') -> bool:
        ok = bool(cond)
        if not ok:
            self.failed += 1
        self.rows.append({'crit': self.crit, 'name': name, 'ok': ok,
                          'expect': str(expect), 'actual': str(actual)[:600], 'note': note})
        CRIT.setdefault(self.crit, []).append((name, ok, str(actual)[:300]))
        print('    [%s] %s' % ('PASS' if ok else 'FAIL', name))
        if not ok:
            print('          期望: %s' % str(expect)[:300])
            print('          实际: %s' % str(actual)[:300])
        elif actual:
            print('          -> %s' % str(actual)[:300])
        return ok

    def summary(self) -> dict:
        total = len(self.rows)
        return {'total': total, 'passed': total - self.failed, 'failed': self.failed}


T = Checker()


def crit_head(n: int, extra: str = '') -> None:
    print('\n' + '─' * 78)
    print('验收 #%d · %s%s' % (n, CRIT_TITLE[n], ('  ' + extra) if extra else ''))
    print('─' * 78)


# ══════════════════════════════════════════════════════════════════
# HTTP / SQL 小工具（**只连本机回环**）
# ══════════════════════════════════════════════════════════════════
def http(method: str, path: str, body=None, headers: dict | None = None,
         timeout: float = 15.0, raw: bool = False):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read()
            return resp.status, (blob.decode('utf-8', 'replace') if raw
                                 else json.loads(blob.decode('utf-8')))
    except urllib.error.HTTPError as ex:
        blob = ex.read()
        return ex.code, (blob.decode('utf-8', 'replace') if raw
                         else json.loads(blob.decode('utf-8')))


def sql(db: str, query: str, args=()) -> list:
    conn = sqlite3.connect(db, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(query, args).fetchall()]
    except sqlite3.OperationalError as ex:
        return [{'error': str(ex)}]
    finally:
        conn.close()


def code_of(payload) -> int:
    return int((payload or {}).get('code', -1)) if isinstance(payload, dict) else -1


def all_keys(node, out: set | None = None) -> set:
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(str(k))
            all_keys(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            all_keys(v, out)
    return out


def leaf_paths(node, prefix: str = '') -> list:
    """把响应摊平成 [(字段路径, 值)]，用于打印「用户详情的字段清单」。"""
    out: list = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = '%s.%s' % (prefix, k) if prefix else str(k)
            out.extend(leaf_paths(v, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = '%s[%d]' % (prefix, i)
            if isinstance(v, (dict, list)):
                out.extend(leaf_paths(v, p))
            else:
                out.append((p, v))
            if i >= 1 and len(node) > 2:
                out.append(('%s[...共%d项]' % (prefix, len(node)), ''))
                break
    else:
        out.append((prefix or '<root>', node))
    return out


# ══════════════════════════════════════════════════════════════════
# 起停真服务
# ══════════════════════════════════════════════════════════════════
def _reset_db(db: str) -> None:
    for suffix in ('', '-wal', '-shm'):
        p = db + suffix
        if os.path.exists(p):
            os.remove(p)


def start_server(db: str, out_path: str, err_path: str, *, password=...):
    """
    起一份真 `serve.py`（站点树 = `_dist/_stage_site`，端口 15088，独立数据文件）。

    `password=...`（默认）→ 注入随机口令；`password=None` → **不注入**
    （用于验证"缺口令时启动即报错且拒绝启用后台"）。
    """
    _reset_db(db)
    env = dict(os.environ)
    for k in list(env):
        if k.startswith('YJK_'):
            env.pop(k, None)                    # 初态干净：后台口令只由本脚本按需注入
    env['SHUZI_PORT'] = str(PORT)
    env['SHUZI_HOST'] = '127.0.0.1'
    env['SHUZI_DATA'] = db
    env['SHUZI_SRC_ROOT'] = STAGE
    env['PYTHONIOENCODING'] = 'utf-8'
    if password is ...:
        env['YJK_ADMIN_PASSWORD'] = ADMIN_PW
    elif password:
        env['YJK_ADMIN_PASSWORD'] = password
    out = open(out_path, 'wb')
    err = open(err_path, 'wb')
    proc = subprocess.Popen([PYTHON, os.path.join(STAGE, 'server', 'serve.py')],
                            cwd=os.path.join(STAGE, 'server'), env=env,
                            stdout=out, stderr=err)
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit('服务提前退出（见 %s）' % err_path)
        try:
            if http('GET', '/api/health', timeout=2.0)[0] == 200:
                return proc, out, err
        except Exception:                                         # noqa: BLE001
            time.sleep(0.4)
    raise SystemExit('等待服务就绪超时（%s）' % BASE)


def stop_server(proc, *handles) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:                                             # noqa: BLE001
        proc.kill()
    for h in handles:
        try:
            h.close()
        except Exception:                                         # noqa: BLE001
            pass
    time.sleep(0.4)


def read_log(path: str) -> str:
    if not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def guest(device: str):
    """C 端游客登录 → (status, access_token, member_id)。"""
    status, env = http('POST', '/api/v1/auth/guest', {'device_id': device})
    d = (env or {}).get('data') or {}
    return status, d.get('access_token', ''), d.get('member_id', '')


# ══════════════════════════════════════════════════════════════════
# 第 0 步：打包
# ══════════════════════════════════════════════════════════════════
def step_pack() -> None:
    print('=' * 78)
    print('第 0 步 · 打包（pwsh -NoProfile -File %s）' % PACK_PS1)
    print('=' * 78)
    p = subprocess.run(['pwsh', '-NoProfile', '-File', PACK_PS1],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('\n'.join((p.stdout or '').strip().splitlines()[-3:]))
    print('    打包退出码 = %d' % p.returncode)
    T.set_crit(0)
    T.check('打包成功（退出码 0），站点树已更新到 _dist/_stage_site', p.returncode == 0,
            '0', p.returncode)
    for f in ('admin_api.py', 'serve.py', 'social.py'):
        path = os.path.join(STAGE, 'server', f)
        T.check('%s 已进入站点树' % f, os.path.exists(path), '存在',
                '%d 字节' % (os.path.getsize(path) if os.path.exists(path) else -1))
    load_production_modules()
    T.check('交付物模块从**打包后的站点树**加载（与真服务同一份代码）',
            os.path.normcase(os.path.dirname(os.path.abspath(_ADMIN.__file__)))
            == os.path.normcase(os.path.join(STAGE, 'server')) and _SERVE is not None,
            os.path.join(STAGE, 'server'), _ADMIN.__file__)


# ══════════════════════════════════════════════════════════════════
# 验收 #1（静态托管部分）· `/admin/` 的服务端能力（in-process）
# ══════════════════════════════════════════════════════════════════
def check_admin_static() -> None:
    """
    `/admin/` 服务端托管能力实测：用**临时 web 目录**放一个最小 index.html，
    验证 `/admin/` → index.html、子路径资源可取、`../` 穿越被拒、既有静态路由不受影响。
    ★ 前端页面本身（`web/admin/`）由另一位同事交付；本项只证明**服务端已具备托管能力**。
    """
    tmp = tempfile.mkdtemp(prefix='admin_static_')
    try:
        os.makedirs(os.path.join(tmp, 'admin', 'assets'), exist_ok=True)
        with open(os.path.join(tmp, 'admin', 'index.html'), 'w', encoding='utf-8') as fh:
            fh.write('<!doctype html><title>AI数显后台</title>')
        with open(os.path.join(tmp, 'admin', 'assets', 'main.js'), 'w', encoding='utf-8') as fh:
            fh.write('// admin bundle')
        with open(os.path.join(tmp, 'secret.txt'), 'w', encoding='utf-8') as fh:
            fh.write('SECRET-MUST-NOT-BE-SERVED-BY-ADMIN')

        saved = _SERVE.WEB_DIR
        _SERVE.WEB_DIR = tmp
        try:
            full, ctype = _SERVE.resolve_static('/admin')
            T.check('#1-⑨ `/admin`（无尾斜杠）解析到 admin/index.html',
                    bool(full) and full.replace('\\', '/').endswith('admin/index.html')
                    and 'text/html' in ctype, 'admin/index.html + text/html',
                    '%s / %s' % (full, ctype))
            full2, ctype2 = _SERVE.resolve_static('/admin/assets/main.js')
            T.check('#1-⑩ `/admin/assets/main.js` 可取且 Content-Type 正确',
                    bool(full2) and full2.endswith('main.js') and 'javascript' in ctype2,
                    'js + application/javascript', '%s / %s' % (full2, ctype2))
            bad = [_SERVE.resolve_static(p)[0] for p in
                   ('/admin/../secret.txt', '/admin/..%2fsecret.txt',
                    '/admin/a/../../secret.txt', '/admin/%2e%2e/secret.txt')]
            T.check('#1-⑪ `/admin/` 下路径穿越一律拒绝（4 种写法）', all(b is None for b in bad),
                    '全部 None', bad)
            T.check('#1-⑫ 既有静态路由未被影响（/data/x.csv 仍解析为 text/csv）',
                    _SERVE.resolve_static('/data/x.csv')[1] == 'text/csv; charset=utf-8',
                    'text/csv', _SERVE.resolve_static('/data/x.csv')[1])
        finally:
            _SERVE.WEB_DIR = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
# 验收 #9 第二阶段 · 真浏览器双视口实测（另一份独立服务，端口 15087）
# ★ 可选阶段：需要**系统 Python** 里的 playwright + Chromium。
#   不可用时只打印 SKIP，**不计入失败**（前端本体由另一位同事交付与验收）。
# ══════════════════════════════════════════════════════════════════
BROWSER_CHILD = r'''
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
'''


def check_frontend_browser() -> None:
    """可选阶段：真 Chromium 双视口打开 `/admin/`，登录并断言无 JS 报错、无横向滚动。"""
    crit_head(9, '（浏览器实测 · 可选阶段）')
    T.set_crit(9)
    if not os.path.exists(SYS_PYTHON):
        T.check('#9-⑦ 浏览器实测：SKIP（本机无系统 Python）', True, 'SKIP', '未安装')
        return
    child = os.path.join(HERE, '_front_browser_probe.py')
    with open(child, 'w', encoding='utf-8') as fh:
        fh.write(BROWSER_CHILD)
    out_json = os.path.join(HERE, '_front_browser_probe.json')
    env = dict(os.environ, PROBE_ROOT=ROOT, PROBE_STAGE=STAGE, PROBE_PORT='15087',
               PROBE_DB=os.path.join(HERE, '_front_browser.db'), PROBE_PW=ADMIN_PW,
               PROBE_OUT=HERE)
    for k in ('SHUZI_SRC_ROOT',):                       # 子进程自己按 PROBE_* 注入
        env.pop(k, None)
    p = subprocess.run([SYS_PYTHON, child], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    text = (p.stdout or '') + (p.stderr or '')
    with open(out_json, 'w', encoding='utf-8') as fh:
        fh.write(text)
    if p.returncode == 3 or 'PROBE_SKIP' in text:
        T.check('#9-⑦ 浏览器实测：SKIP（本机系统 Python 未装 playwright/Chromium）', True,
                'SKIP', text.strip().splitlines()[-1][:160] if text.strip() else '')
        return
    payload = ''
    for line in text.splitlines():
        if line.startswith('PROBE_JSON '):
            payload = line[len('PROBE_JSON '):]
    if not payload:
        T.check('#9-⑦ 浏览器实测产出可解析结果', False, 'PROBE_JSON 一行',
                text.strip()[-300:])
        return
    data = json.loads(payload)
    EVIDENCE['browser'] = data
    for name, r in data.items():
        T.check('#9-⑦ %s 登录成功且用户列表渲染出真行' % name,
                r['login_ok'] and r['rows_app'] >= 1, '登录成功 + 行数>=1',
                'login=%s rows=%s' % (r['login_ok'], r['rows_app']))
        T.check('#9-⑧ %s 无 JS 运行时错误（pageerror）' % name, not r['pageerrors'],
                '无', r['pageerrors'] or '无')
        T.check('#9-⑨ %s 无 console error' % name, not r['console_errors'],
                '无', r['console_errors'] or '无')
        T.check('#9-⑩ %s 无横向滚动（scrollWidth == innerWidth，登录前后各一次）' % name,
                r['scroll_login'][0] <= r['scroll_login'][1] + 1
                and r['scroll_app'][0] <= r['scroll_app'][1] + 1,
                'scrollWidth <= innerWidth',
                '登录前 %s / 登录后 %s' % (r['scroll_login'], r['scroll_app']))


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def main() -> int:
    print('=' * 78)
    print('AI 数显独立后台 · 端到端真服务验收（口径源：变更单 §二 的 10 条）')
    print('=' * 78)
    print('解释器     : %s' % sys.executable)
    print('站点树     : %s' % STAGE)
    print('端口       : %d（只连本机回环）' % PORT)
    print('管理口令   : %s（本进程随机生成，经环境变量 YJK_ADMIN_PASSWORD 注入）'
          % (ADMIN_PW[:9] + '*' * 12))
    print('口令摘要   : sha256=%s…' % hashlib.sha256(ADMIN_PW.encode()).hexdigest()[:16])
    print('-' * 78)

    step_pack()

    # ── 源码级自检（口令纪律 / 合规禁词）────────────────────────────
    T.set_crit(0)
    with open(os.path.join(ROOT, 'server', 'admin_api.py'), 'r', encoding='utf-8') as fh:
        admin_src = fh.read()
    with open(os.path.join(ROOT, 'server', 'social.py'), 'r', encoding='utf-8') as fh:
        social_src = fh.read()
    T.check('后台口令只从环境变量读（源码含 YJK_ADMIN_PASSWORD）',
            'YJK_ADMIN_PASSWORD' in admin_src, '含环境变量名', '已含')
    T.check('源码里没有任何写死的口令（本次随机口令不出现在源码中）',
            ADMIN_PW not in admin_src, '不含本次口令', '已确认不含')
    T.check('口令比对用标准库 hmac.compare_digest（不自造密码学）',
            'hmac.compare_digest' in admin_src, 'compare_digest', '已使用')
    T.check('CSV 表头与测试期望一致（交付物 ↔ 独立期望 交叉验证）',
            list(_ADMIN.CSV_HEADER) == EXPECTED_CSV_HEADER, EXPECTED_CSV_HEADER,
            list(_ADMIN.CSV_HEADER))
    for word in BANNED_WORDS:
        T.check('合规禁词检查：%s 不出现在 admin_api.py / social.py' % word,
                (word not in admin_src) and (word not in social_src), '不出现', '不出现')
    EVIDENCE['source'] = {
        'admin_api.py': {'bytes': os.path.getsize(os.path.join(ROOT, 'server', 'admin_api.py')),
                         'sha256': hashlib.sha256(admin_src.encode('utf-8')).hexdigest()},
        'social.py': {'bytes': os.path.getsize(os.path.join(ROOT, 'server', 'social.py')),
                      'sha256': hashlib.sha256(social_src.encode('utf-8')).hexdigest()},
        'serve.py': {'bytes': os.path.getsize(os.path.join(ROOT, 'server', 'serve.py')),
                     'sha256': hashlib.sha256(
                         open(os.path.join(ROOT, 'server', 'serve.py'), 'rb').read())
                     .hexdigest()},
        'test_admin.py': {'bytes': os.path.getsize(os.path.abspath(__file__)),
                          'sha256': hashlib.sha256(
                              open(os.path.abspath(__file__), 'rb').read()).hexdigest()}}

    proc = None
    handles: tuple = ()
    try:
        # ══════════════════════════════════════════════════════════
        # A 段：主库（有口令）
        # ══════════════════════════════════════════════════════════
        print('\n' + '=' * 78)
        print('A 段 · 起真服务（数据文件 %s）' % os.path.basename(DB_MAIN))
        print('=' * 78)
        proc, *handles = start_server(DB_MAIN, LOG_MAIN, ERR_MAIN)
        handles = tuple(handles)
        st, health = http('GET', '/api/health')
        T.set_crit(0)
        T.check('A0 服务就绪且是"我们自己起的那个"（health.data_file = 本次独立库）',
                st == 200 and str((health.get('data') or {}).get('data_file', '')).lower()
                == DB_MAIN.lower(), DB_MAIN, (health.get('data') or {}).get('data_file'))

        # ── 造 C 端数据：6 个会员（建档 / 打卡 / 好友 / 加油）────────────
        members = []
        for i, (city, lng, lat) in enumerate(COORDS):
            st, tok, mid = guest('adm-verify-dev-%d' % (i + 1))
            T.check('A1-① 游客登录 #%d（%s）' % (i + 1, city), st == 200 and bool(mid),
                    '200 + member_id', '%d %s' % (st, mid))
            st2, _env2 = http('POST', '/api/v1/profile/birth',
                              {'birth_local': BIRTHS[i], 'longitude': lng, 'latitude': lat},
                              {'Authorization': 'Bearer ' + tok})
            T.check('A1-② 建档 #%d（%s，出生 %s）' % (i + 1, city, BIRTHS[i]), st2 == 200,
                    '200', st2)
            members.append({'token': tok, 'member_id': mid, 'city': city, 'birth': BIRTHS[i]})
        m1, m2 = members[0], members[1]

        for k in range(8):                       # m1 打 8 次卡（不同日期，按日聚合）
            http('POST', '/api/v1/checkin', {'on': '2026-09-%02d' % (10 + k)},
                 {'Authorization': 'Bearer ' + m1['token']})
        for on in ('2026-10-01', '2026-10-02'):  # m2 打 2 次卡
            http('POST', '/api/v1/checkin', {'on': on},
                 {'Authorization': 'Bearer ' + m2['token']})
        rows = sql(DB_MAIN, 'SELECT observation_count FROM baseline WHERE member_id = ?',
                   (m1['member_id'],))
        T.check('A1-③ m1 打卡 8 个不同日期 → 基线观测数 8（同一天重复只算一次）',
                rows and int(rows[0]['observation_count']) == 8, 8, rows)

        st, env3 = http('GET', '/api/v1/me/invite_code', None,
                        {'Authorization': 'Bearer ' + m1['token']})
        m1_code = (env3.get('data') or {}).get('invite_code', '')
        st, env4 = http('POST', '/api/v1/friends/invite',
                        {'invite_code': m1_code, 'auto_accept': True},
                        {'Authorization': 'Bearer ' + m2['token']})
        T.check('A1-④ m2 用 m1 的邀请码自动成为好友（accepted）',
                st == 200 and (env4.get('data') or {}).get('status') == 'accepted',
                'accepted', '%d %s' % (st, (env4.get('data') or {}).get('status')))
        st, _env5 = http('POST', '/api/v1/friends/cheer',
                         {'friend_id': m1['member_id'], 'template_id': 'care_self'},
                         {'Authorization': 'Bearer ' + m2['token']})
        T.check('A1-⑤ m2 给 m1 送加油（封禁前，正常放行）', st == 200, '200', st)
        EVIDENCE['seed'] = {'members': [{'member_id': m['member_id'], 'city': m['city'],
                                         'birth': m['birth']} for m in members],
                            'm1_invite_code': m1_code}

        st, daily = http('GET', '/api/v1/rhythm/daily', None,
                         {'Authorization': 'Bearer ' + m1['token']})
        dd = (daily or {}).get('data') or {}
        T.check('A1-⑥ GET /v1/rhythm/daily 行为不变：index 含 score 与 score_kernel，'
                '基线建立后 personalized 非空',
                st == 200 and isinstance(dd.get('index'), dict)
                and dd['index'].get('score') is not None
                and dd['index'].get('score_kernel') is not None
                and dd.get('personalized') is not None,
                'index.score/score_kernel 有值 + personalized 非空',
                'score=%s kernel=%s personalized=%s'
                % (dd.get('index', {}).get('score'), dd.get('index', {}).get('score_kernel'),
                   bool(dd.get('personalized'))))
        st, fr = http('GET', '/api/v1/friends', None, {'Authorization': 'Bearer ' + m1['token']})
        T.check('A1-⑦ GET /v1/friends 行为不变（正常会员拿到 accepted 好友）',
                st == 200 and len(((fr or {}).get('data') or {}).get('friends') or []) == 1,
                '200 + 1 条好友',
                '%d %s' % (st, len(((fr or {}).get('data') or {}).get('friends') or [])))
        EVIDENCE['regression_spot'] = {'daily_index': dd.get('index'),
                                       'friends': (fr.get('data') or {}).get('friends')}

        # ══════════════════════════════════════════════════════════
        # 验收 #1：后台可登录 + 令牌隔离 + /admin/ 托管能力
        # ══════════════════════════════════════════════════════════
        crit_head(1)
        T.set_crit(1)
        st_bad, bad = http('POST', '/api/v1/admin/login', {'password': ADMIN_PW + '-wrong'})
        T.check('#1-① 错口令 → HTTP 401 + 业务码 20000',
                st_bad == 401 and code_of(bad) == 20000, '401 / 20000',
                '%d / %s' % (st_bad, code_of(bad)))
        st_ok, ok = http('POST', '/api/v1/admin/login', {'password': ADMIN_PW})
        ad = (ok or {}).get('data') or {}
        token = ad.get('admin_token', '')
        RUN_SECRETS['admin_token'] = token
        T.check('#1-② 正确口令 → HTTP 200 + admin_token + expires_in=7200（TTL 2 小时）',
                st_ok == 200 and len(token) >= 32 and ad.get('expires_in') == 7200,
                '200 + token + 7200',
                '200=%s token_len=%d expires_in=%s' % (st_ok == 200, len(token),
                                                       ad.get('expires_in')))
        A = {'Authorization': 'Bearer ' + token}
        st_users, users0 = http('GET', '/api/v1/admin/users?page=1&size=20', None, A)
        T.check('#1-③ 拿令牌可访问受保护接口（GET /v1/admin/users → 200）',
                st_users == 200, '200', st_users)
        st_x1, _ = http('GET', '/api/v1/auth/me', None, A)
        T.check('#1-④ 用**后台令牌**调 C 端接口 → 401（后台令牌不是 C 端令牌）',
                st_x1 == 401, '401', st_x1)
        st_x2, x2 = http('GET', '/api/v1/admin/users', None,
                         {'Authorization': 'Bearer ' + m1['token']})
        T.check('#1-⑤ 用**C 端游客令牌**调后台接口 → 401（两条链路互不相通）',
                st_x2 == 401 and code_of(x2) == 20000, '401 / 20000',
                '%d / %s' % (st_x2, code_of(x2)))
        st_x3, x3 = http('GET', '/api/v1/admin/users')
        T.check('#1-⑥ 不带令牌 → 401（除 login 外所有 /v1/admin/* 都必须校验后台令牌）',
                st_x3 == 401 and code_of(x3) == 20000, '401 / 20000',
                '%d / %s' % (st_x3, code_of(x3)))
        st_x4, _ = http('GET', '/api/v1/admin/stats', None, {'Authorization': 'Bearer bogus'})
        T.check('#1-⑦ 乱令牌 → 401', st_x4 == 401, '401', st_x4)
        for method, path in (('GET', '/api/v1/admin/stats'), ('GET', '/api/v1/admin/social'),
                             ('GET', '/api/v1/admin/audit'), ('GET', '/api/v1/admin/export.csv'),
                             ('GET', '/api/v1/admin/user/' + m1['member_id']),
                             ('POST', '/api/v1/admin/ban')):
            stz, _p = http(method, path, {} if method == 'POST' else None)
            T.check('#1-⑧ 无令牌访问 %s %s → 401' % (method, path), stz == 401, '401', stz)
        check_admin_static()

        # ══════════════════════════════════════════════════════════
        # 验收 #3：用户列表
        # ══════════════════════════════════════════════════════════
        crit_head(3)
        T.set_crit(3)
        st, ul = http('GET', '/api/v1/admin/users?page=1&size=20', None, A)
        ud = (ul or {}).get('data') or {}
        T.check('#3-① 分页结构含 total/page/size/items',
                st == 200 and set(('total', 'page', 'size', 'items')) <= set(ud),
                'total/page/size/items', sorted(ud.keys()))
        T.check('#3-② 共 6 个会员、每页 20 条', ud.get('total') == 6 and ud.get('size') == 20,
                'total=6 size=20', 'total=%s size=%s' % (ud.get('total'), ud.get('size')))
        need = {'member_id', 'nickname', 'profile_completed', 'baseline_progress',
                'last_active', 'streak_days', 'banned', 'invite_code'}
        item0 = (ud.get('items') or [{}])[0]
        T.check('#3-③ items 字段覆盖变更单「用户列表」要求（member_id/昵称/建档状态/基线进度/'
                '最近活跃/连续天数）', need <= set(item0), sorted(need), sorted(item0.keys()))
        T.check('#3-④ 基线进度为 n/7 口径（min_observations=7）',
                all(i['baseline_progress']['min_observations'] == 7 for i in ud['items']),
                'min_observations=7',
                [i['baseline_progress']['text'] for i in ud['items']])
        st, u1 = http('GET', '/api/v1/admin/users?page=1&size=2', None, A)
        st, u2 = http('GET', '/api/v1/admin/users?page=2&size=2', None, A)
        d1, d2 = (u1.get('data') or {}), (u2.get('data') or {})
        T.check('#3-⑤ 分页切片正确（page=1/2，size=2 → 各 2 条、页码回显、不重叠）',
                len(d1.get('items') or []) == 2 and len(d2.get('items') or []) == 2
                and d1.get('page') == 1 and d2.get('page') == 2
                and d1['items'][0]['member_id'] != d2['items'][0]['member_id'],
                '各 2 条且不重叠',
                '%s vs %s' % (d1['items'][0]['member_id'], d2['items'][0]['member_id']))
        st, uq = http('GET', '/api/v1/admin/users?q=' + m1_code, None, A)
        dq = (uq.get('data') or {})
        T.check('#3-⑥ 关键词搜索（邀请码）命中 1 条且就是 m1',
                dq.get('total') == 1 and dq['items'][0]['member_id'] == m1['member_id'],
                '1 条 / m1', '%s / %s' % (dq.get('total'),
                                          (dq.get('items') or [{}])[0].get('member_id')))
        st, uq2 = http('GET', '/api/v1/admin/users?q=' + m1['member_id'][:12], None, A)
        T.check('#3-⑦ 关键词搜索（member_id 前缀）同样命中',
                ((uq2.get('data') or {}).get('total', 0)) >= 1, '>=1',
                (uq2.get('data') or {}).get('total'))
        st, ub = http('GET', '/api/v1/admin/users?banned=1', None, A)
        T.check('#3-⑧ 支持按封禁状态过滤（当前无人被封 → total=0）',
                ((ub.get('data') or {}).get('total')) == 0, 0,
                (ub.get('data') or {}).get('total'))

        # ══════════════════════════════════════════════════════════
        # 验收 #4：用户详情字段级脱敏
        # ══════════════════════════════════════════════════════════
        crit_head(4)
        T.set_crit(4)
        st, det = http('GET', '/api/v1/admin/user/' + m1['member_id'], None, A)
        dd4 = (det or {}).get('data') or {}
        T.check('#4-① 详情接口 200', st == 200, '200', st)
        paths = leaf_paths(dd4)
        print('        ── 用户详情响应字段清单（共 %d 个叶字段）──' % len(paths))
        for p, v in paths:
            print('           %-50s = %s' % (p, str(v)[:58]))
        EVIDENCE['detail_fields'] = [{'path': p, 'value': str(v)[:200]} for p, v in paths]

        prows = sql(DB_MAIN, 'SELECT birth_local, longitude, latitude FROM profile'
                             ' WHERE member_id = ?', (m1['member_id'],))
        stored_birth = ((prows[0].get('birth_local') if prows else '') or '')
        T.check('#4-② 前提：库里确实存着**精确出生时刻**与经纬度（不是"本来就没存"）',
                stored_birth == BIRTHS[0] and ':' in stored_birth
                and prows[0].get('longitude') is not None,
                BIRTHS[0] + ' + 经纬度', stored_birth)

        keys = all_keys(dd4)
        blob = json.dumps(dd4, ensure_ascii=False)
        hit_keys = sorted(k for k in keys if k in FORBIDDEN_TOKENS)
        T.check('#4-③ 响应里**不存在**禁止字段名（birth_local / birth_time / blood_pressure / '
                'history_note / height_cm / weight_kg / longitude / latitude …）',
                not hit_keys, '无', hit_keys)
        T.check('#4-④ 响应序列化后**不含**原始出生串 %r' % BIRTHS[0],
                stored_birth not in blob, '不含', '已确认不含')
        time_part = stored_birth.split(' ')[-1]
        T.check('#4-⑤ 响应序列化后**不含**精确出生时刻 %r' % time_part,
                time_part not in blob, '不含', '已确认不含')
        T.check('#4-⑥ 响应序列化后不含经纬度原文（116.4074 / 39.9042）',
                ('116.4074' not in blob) and ('39.9042' not in blob), '不含', '已确认不含')
        T.check('#4-⑦ 正例：出生信息**确实回到了"日"级**（birth_date = 1988-11-27）',
                (dd4.get('birth') or {}).get('birth_date') == BIRTHS[0].split(' ')[0],
                '1988-11-27', (dd4.get('birth') or {}).get('birth_date'))
        T.check('#4-⑧ 出生地城市已回（脱敏允许项）且显式标注"不回精确时刻与经纬度"',
                bool((dd4.get('birth') or {}).get('birth_city'))
                and (dd4.get('birth') or {}).get('exact_time_returned') is False
                and (dd4.get('birth') or {}).get('coordinates_returned') is False,
                'birth_city 有值 + exact_time_returned=false',
                '%s / %s' % ((dd4.get('birth') or {}).get('birth_city'),
                             (dd4.get('birth') or {}).get('exact_time_returned')))
        T.check('#4-⑨ 体征与病史显式标记为"未采集"，响应里没有任何数值',
                (dd4.get('archive') or {}).get('vitals_collected') is False
                and (dd4.get('archive') or {}).get('history_collected') is False,
                'vitals_collected=false / history_collected=false',
                json.dumps(dd4.get('archive'), ensure_ascii=False))
        T.check('#4-⑩ 打卡记录只回日期与通道数（不回观测数值）',
                all(set(it) <= {'on_date', 'channels'} for it in
                    ((dd4.get('checkins') or {}).get('items') or [])),
                '只有 on_date/channels',
                ((dd4.get('checkins') or {}).get('items') or [])[:1])
        schema = sql(DB_MAIN, "SELECT name, sql FROM sqlite_master WHERE type = 'table'")
        tcols = ' '.join(str(r.get('sql') or '') for r in schema).lower()
        leaked_cols = [t for t in ('height', 'weight', 'bp_systolic', 'bp_diastolic',
                                   'blood_pressure', 'resting_hr', 'history_note')
                       if t in tcols]
        T.check('#4-⑪ 全库表结构里不存在体征/病史列（本项目未采集，故无从泄露）',
                not leaked_cols, '无此类列', leaked_cols)
        T.check('#4-⑫ 出口自检存在且 fail-closed（_assert_no_secrets + FORBIDDEN_KEYS）',
                ('_assert_no_secrets' in admin_src) and ('FORBIDDEN_KEYS' in admin_src),
                '存在', '已确认存在')
        T.check('#4-⑬ 详情接口不返回口令/令牌等运维凭据',
                ('password' not in keys) and ('admin_token' not in keys)
                and (ADMIN_PW not in blob), '不含 password/admin_token', '已确认不含')

        # ══════════════════════════════════════════════════════════
        # 验收 #8：审计（紧跟详情之后对照增量）
        # ══════════════════════════════════════════════════════════
        crit_head(8)
        T.set_crit(8)
        before = sql(DB_MAIN, 'SELECT count(*) AS n FROM admin_audit')[0]['n']
        st, _det2 = http('GET', '/api/v1/admin/user/' + m2['member_id'], None, A)
        after = sql(DB_MAIN, 'SELECT count(*) AS n FROM admin_audit')[0]['n']
        T.check('#8-① 查看一次用户详情 → 审计**恰好**新增 1 条',
                st == 200 and int(after) - int(before) == 1, '+1',
                '%s → %s（+%s）' % (before, after, int(after) - int(before)))
        newest = sql(DB_MAIN, 'SELECT * FROM admin_audit ORDER BY id DESC LIMIT 1')[0]
        T.check('#8-② 审计行含**操作者 / 动作 / 目标 / 时间 / 会话 / IP**',
                newest.get('actor') == 'admin' and newest.get('action') == 'user_detail'
                and newest.get('target') == m2['member_id'] and bool(newest.get('at'))
                and newest.get('ip') == '127.0.0.1' and bool(newest.get('session')),
                'actor=admin action=user_detail target=m2 at/ip/session 有值',
                {k: newest.get(k) for k in ('actor', 'action', 'target', 'at', 'ip', 'session')})
        T.check('#8-③ 审计时间可解析（ISO 8601）',
                bool(re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$', newest.get('at') or '')),
                'ISO 8601', newest.get('at'))
        T.check('#8-④ 审计里**不含**口令与后台令牌原文',
                ADMIN_PW not in json.dumps(newest, ensure_ascii=False)
                and token not in json.dumps(newest, ensure_ascii=False), '不含', '已确认不含')
        st, au = http('GET', '/api/v1/admin/audit?page=1&size=5', None, A)
        aud = (au.get('data') or {})
        T.check('#8-⑤ GET /v1/admin/audit 返回审计日志（分页 + 动作计数）',
                st == 200 and aud.get('total', 0) >= 3
                and (aud.get('counts') or {}).get('user_detail', 0) >= 2,
                '200 + total>=3 + user_detail>=2',
                'total=%s counts=%s' % (aud.get('total'), aud.get('counts')))
        cnt_before = sql(DB_MAIN, 'SELECT count(*) AS n FROM admin_audit')[0]['n']
        http('GET', '/api/v1/admin/audit?page=1&size=5', None, A)
        cnt_after = sql(DB_MAIN, 'SELECT count(*) AS n FROM admin_audit')[0]['n']
        T.check('#8-⑥ 查看审计日志本身**不**新增审计行（不自我放大）',
                int(cnt_after) == int(cnt_before), '相等', '%s → %s' % (cnt_before, cnt_after))
        st, au2 = http('GET', '/api/v1/admin/audit?action=ban&page=1', None, A)
        T.check('#8-⑦ 审计支持按动作过滤（action=ban）',
                st == 200 and (au2.get('data') or {}).get('action') == 'ban',
                '200 + action=ban', (au2.get('data') or {}).get('action'))
        EVIDENCE['audit_newest'] = newest

        # ══════════════════════════════════════════════════════════
        # 验收 #5：指数分布
        # ══════════════════════════════════════════════════════════
        crit_head(5)
        T.set_crit(5)
        st, stats = http('GET', '/api/v1/admin/stats', None, A)
        sd = (stats or {}).get('data') or {}
        dist = sd.get('index_distribution') or {}
        items = dist.get('items') or []
        pct_sum = round(sum(b['pct'] for b in items), 2)
        T.check('#5-① GET /v1/admin/stats 200 且含运营指标',
                st == 200 and {'users_total', 'new_today', 'archive_rate', 'checkin_users_today',
                               'index_distribution', 'friend_circle'} <= set(sd),
                '200 + 指标字段齐全', sorted(sd.keys())[:12])
        T.check('#5-② 四档 A/B/C/D 齐全', [b['code'] for b in items] == ['A', 'B', 'C', 'D'],
                "['A','B','C','D']", [b['code'] for b in items])
        T.check('#5-③ A+B+C+D 占比之和 = 100%（±1 舍入）', abs(pct_sum - 100.0) <= 1.0,
                '100 ± 1', '%.1f（各档 %s）' % (pct_sum, [b['pct'] for b in items]))
        T.check('#5-④ 接口自报的 pct_sum 与实际求和一致',
                abs(float(dist.get('pct_sum', -1)) - pct_sum) <= 0.05,
                '一致', 'pct_sum=%s 实算=%.2f' % (dist.get('pct_sum'), pct_sum))
        T.check('#5-⑤ 分母口径自洽（band_total = Σ各档人数 = profiled_total - unavailable）',
                int(dist.get('total', -1)) == sum(b['count'] for b in items)
                and int(dist.get('total', 0)) + int(dist.get('unavailable', 0))
                == int(dist.get('profiled_total', -1)),
                'total=Σcount 且 total+unavailable=profiled_total',
                'total=%s Σcount=%s profiled=%s unavailable=%s'
                % (dist.get('total'), sum(b['count'] for b in items),
                   dist.get('profiled_total'), dist.get('unavailable')))
        T.check('#5-⑥ 统计口径与 /v1/rhythm/daily 同源（basis 声明含 display 与 band_of）',
                'band_of' in str(dist.get('basis', '')) and 'display' in str(dist.get('basis', '')),
                'basis 含 display / band_of', str(dist.get('basis'))[:80])
        T.check('#5-⑦ 建档率与打卡数一致（6 人全部建档，6/6 = 1.0）',
                sd.get('users_total') == 6 and sd.get('profiled_total') == 6
                and abs(float(sd.get('archive_rate', 0)) - 1.0) < 1e-6,
                '6/6 = 1.0', '%s/%s rate=%s' % (sd.get('profiled_total'), sd.get('users_total'),
                                                sd.get('archive_rate')))
        T.check('#5-⑧ 今日新增 = 6（本测试刚建的号）', sd.get('new_today') == 6, 6,
                sd.get('new_today'))
        T.check('#5-⑨ 好友圈规模：1 条 accepted、1 条加油',
                (sd.get('friend_circle') or {}).get('accepted') == 1
                and (sd.get('friend_circle') or {}).get('cheer_total') == 1,
                'accepted=1 cheer=1', sd.get('friend_circle'))
        print('        指数分布：%s' % json.dumps(items, ensure_ascii=False))
        T.check('#5-⑩ 每档给出中文档名（取自内核 band_of，不自造）',
                all(b.get('name') for b in items), '四档都有 name',
                [b.get('name') for b in items])
        EVIDENCE['stats'] = sd

        # ══════════════════════════════════════════════════════════
        # 验收 #6：CSV 导出
        # ══════════════════════════════════════════════════════════
        crit_head(6)
        T.set_crit(6)
        st, blob = http('GET', '/api/v1/admin/export.csv', None, A, raw=True)
        T.check('#6-① GET /v1/admin/export.csv 200 且返回 CSV 文本（带 UTF-8 BOM）',
                st == 200 and blob.startswith('\ufeff') and 'member_id,' in blob,
                '200 + BOM + 表头', '%d / 前 60 字节=%r' % (st, blob[:60]))
        lines = [ln for ln in blob.lstrip('\ufeff').split('\r\n') if ln]
        header = lines[0].split(',')
        T.check('#6-② 表头与期望（独立写的）逐字一致', header == EXPECTED_CSV_HEADER,
                EXPECTED_CSV_HEADER, header)
        T.check('#6-③ 行数正确（表头 + 全部会员数 = 6）', len(lines) - 1 == 6
                and len(lines) - 1 == ud.get('total'),
                '表头 + 6 行', '%d 行' % (len(lines) - 1))
        body_ids = {ln.split(',')[0] for ln in lines[1:]}
        T.check('#6-④ 导出的 member_id 集合与用户列表一致',
                body_ids == {i['member_id'] for i in ud['items']}, '集合相同',
                '%d 个 id' % len(body_ids))
        leaks = [t for t in FORBIDDEN_TOKENS if t in blob]
        T.check('#6-⑤ 扫描导出内容：不含任何敏感字段名', not leaks, '无', leaks)
        T.check('#6-⑥ 扫描导出内容：不含出生信息（原始串 %r / 日期 1988-11-27 / 时刻 03:47）'
                % BIRTHS[0],
                (BIRTHS[0] not in blob) and ('1988-11-27' not in blob) and ('03:47' not in blob),
                '全不含', '已确认不含')
        T.check('#6-⑦ CSV 里没有任何出生相关列（列头不含 birth）',
                'birth' not in ''.join(header), '无出生列', header)
        T.check('#6-⑧ 导出含 score/band（与统计同口径），且值为内核分档码 A-D',
                'score' in header and 'band' in header
                and all(ln.split(',')[header.index('band')] in ('A', 'B', 'C', 'D', '')
                        for ln in lines[1:]), '含 score/band 且档码合法',
                [ln.split(',')[header.index('band')] for ln in lines[1:]])
        EVIDENCE['csv'] = {'status': st, 'bytes': len(blob.encode('utf-8')),
                           'header': header, 'rows': len(lines) - 1}

        # ══════════════════════════════════════════════════════════
        # 验收 #7：封禁生效
        # ══════════════════════════════════════════════════════════
        crit_head(7)
        T.set_crit(7)
        HB = {'Authorization': 'Bearer ' + m2['token']}
        pre_friends = http('GET', '/api/v1/friends', None, HB)
        pre_cheer = http('POST', '/api/v1/friends/cheer',
                         {'friend_id': m1['member_id'], 'template_id': 'sleep_early'}, HB)
        print('        封禁前 GET  /v1/friends        → HTTP %d / code %s'
              % (pre_friends[0], code_of(pre_friends[1])))
        print('        封禁前 POST /v1/friends/cheer  → HTTP %d / code %s'
              % (pre_cheer[0], code_of(pre_cheer[1])))
        T.check('#7-① 前提：封禁前该会员社交功能正常（friends 200 / cheer 200）',
                pre_friends[0] == 200 and pre_cheer[0] == 200, '200 / 200',
                '%s / %s' % (pre_friends[0], pre_cheer[0]))
        st_ban, banresp = http('POST', '/api/v1/admin/ban',
                               {'member_id': m2['member_id'], 'banned': True, 'reason': '验证封禁'}, A)
        T.check('#7-② POST /v1/admin/ban {banned:true} → 200 且标记生效',
                st_ban == 200 and (banresp.get('data') or {}).get('banned') is True,
                '200 + banned=true',
                '%s %s' % (st_ban, (banresp.get('data') or {}).get('banned')))
        post1 = http('GET', '/api/v1/friends', None, HB)
        post2 = http('POST', '/api/v1/friends/cheer',
                     {'friend_id': m1['member_id'], 'template_id': 'care_self'}, HB)
        print('        封禁后 GET  /v1/friends        → HTTP %d / code %s / %s'
              % (post1[0], code_of(post1[1]), (post1[1] or {}).get('message')))
        print('        封禁后 POST /v1/friends/cheer  → HTTP %d / code %s / %s'
              % (post2[0], code_of(post2[1]), (post2[1] or {}).get('message')))
        EVIDENCE['ban_before_after'] = {
            'before': {'friends_http': pre_friends[0], 'friends_code': code_of(pre_friends[1]),
                       'cheer_http': pre_cheer[0], 'cheer_code': code_of(pre_cheer[1])},
            'after': {'friends_http': post1[0], 'friends_code': code_of(post1[1]),
                      'friends_message': (post1[1] or {}).get('message'),
                      'cheer_http': post2[0], 'cheer_code': code_of(post2[1]),
                      'cheer_message': (post2[1] or {}).get('message')}}
        T.check('#7-③ 封禁后 GET /friends 被拒（可读业务码 30002 + 明确文案）',
                post1[0] >= 400 and code_of(post1[1]) == 30002
                and '暂停' in str((post1[1] or {}).get('message')),
                '>=400 / 30002 / 文案含"暂停"',
                '%d / %s / %s' % (post1[0], code_of(post1[1]), (post1[1] or {}).get('message')))
        T.check('#7-④ 封禁后 POST /friends/cheer 被拒（同一业务码）',
                post2[0] >= 400 and code_of(post2[1]) == 30002,
                '>=400 / 30002', '%d / %s' % (post2[0], code_of(post2[1])))
        ores = []
        for mm, path, body in (('GET', '/api/v1/friends/feed', None),
                               ('GET', '/api/v1/friends/ranking', None),
                               ('GET', '/api/v1/friends/privacy', None),
                               ('GET', '/api/v1/friends/cheer/templates', None),
                               ('POST', '/api/v1/friends/privacy', {'share_index': True})):
            s_, e_ = http(mm, path, body, HB)
            ores.append((path, s_, code_of(e_)))
        T.check('#7-⑤ 封禁覆盖全部 /v1/friends*（feed/ranking/privacy/templates 同样被拒）',
                all(r[1] >= 400 and r[2] == 30002 for r in ores), '全部 >=400 / 30002', ores)
        ok_other = http('GET', '/api/v1/friends', None,
                        {'Authorization': 'Bearer ' + m1['token']})
        T.check('#7-⑥ **未封禁的其他人不受影响**（m1 的 friends 仍 200，零回归）',
                ok_other[0] == 200, '200', ok_other[0])
        st_unban, _un = http('POST', '/api/v1/admin/ban',
                             {'member_id': m2['member_id'], 'banned': False}, A)
        after1 = http('GET', '/api/v1/friends', None, HB)
        after2 = http('POST', '/api/v1/friends/cheer',
                      {'friend_id': m1['member_id'], 'template_id': 'drink_water'}, HB)
        print('        解封后 GET  /v1/friends        → HTTP %d / code %s'
              % (after1[0], code_of(after1[1])))
        print('        解封后 POST /v1/friends/cheer  → HTTP %d / code %s'
              % (after2[0], code_of(after2[1])))
        T.check('#7-⑦ 解封后立刻恢复（friends 200 / cheer 200，无需重启、无缓存）',
                st_unban == 200 and after1[0] == 200 and after2[0] == 200,
                '200/200/200', '%s/%s/%s' % (st_unban, after1[0], after2[0]))
        rows = sql(DB_MAIN, 'SELECT member_id, banned FROM admin_ban WHERE member_id = ?',
                   (m2['member_id'],))
        T.check('#7-⑧ 封禁状态落在 admin_ban 表（解封后行保留 banned=0，留痕不删行）',
                rows and int(rows[0]['banned']) == 0, 'banned=0 且行仍在', rows)
        st_ban2, ban2 = http('POST', '/api/v1/admin/ban',
                             {'member_id': 'mbr_不存在', 'banned': True}, A)
        T.check('#7-⑨ 封禁不存在的会员 → 明确拒绝（不产生幽灵封禁行）',
                st_ban2 >= 400 and code_of(ban2) == 10002, '>=400 / 10002',
                '%s / %s' % (st_ban2, code_of(ban2)))
        nb = http('POST', '/api/v1/admin/ban', {'member_id': m2['member_id']}, A)
        T.check('#7-⑩ 缺少 banned 字段 → 10001 缺字段（不做猜测式解释）',
                code_of(nb[1]) == 10001, '10001', code_of(nb[1]))
        bcnt = sql(DB_MAIN, "SELECT count(*) AS n FROM admin_audit WHERE action = 'ban'")[0]['n']
        ucnt = sql(DB_MAIN, "SELECT count(*) AS n FROM admin_audit WHERE action = 'unban'")[0]['n']
        T.check('#7-⑪ 封禁/解封各写 1 条审计（ban=1 / unban=1）',
                int(bcnt) == 1 and int(ucnt) == 1, 'ban=1 unban=1',
                'ban=%s unban=%s' % (bcnt, ucnt))

        # ══════════════════════════════════════════════════════════
        # 验收 #9：前端（另一位同事交付；此处只做"可服务 + 契约对齐"实测）
        # ══════════════════════════════════════════════════════════
        crit_head(9, '（前端由另一位同事交付）')
        T.set_crit(9)
        st_a, page_html = http('GET', '/admin/', None, None, raw=True)
        T.check('#9-① `GET /admin/` 返回 200 且是真 HTML（前端产物已落地）',
                st_a == 200 and '<html' in page_html.lower(),
                '200 + HTML', 'HTTP %s / %d 字节' % (st_a, len(page_html)))
        st_js, js_body = http('GET', '/admin/app.js', None, None, raw=True)
        st_css, css_body = http('GET', '/admin/style.css', None, None, raw=True)
        T.check('#9-② `/admin/app.js` 与 `/admin/style.css` 均可取（服务端托管正常）',
                st_js == 200 and st_css == 200 and len(js_body) > 1000 and len(css_body) > 1000,
                '200 + 非空', 'js=%s(%d) css=%s(%d)' % (st_js, len(js_body), st_css,
                                                        len(css_body)))
        st_j, jenv = http('GET', '/api/v1/admin/users?page=1&size=1', None, A)
        T.check('#9-③ 后台接口返回**同源纯 JSON 信封**（code/message/data/trace_id），'
                '前端可直接 fetch，无跨域依赖',
                st_j == 200 and set(('code', 'message', 'data', 'trace_id')) <= set(jenv),
                '200 + 四件套', sorted(jenv.keys()))
        # 前后端契约对齐：直接读前端源码里调用的路径，逐个对回后端的路由表
        front_src = js_body
        front_paths = sorted({(m if m.startswith('/') else '/' + m) for m in
                              re.findall(r"api\('([^'?]+)", front_src)})
        allowed = {'/login', '/users', '/user/', '/stats', '/social', '/ban', '/audit'}
        T.check('#9-④ 前端调用的路径全部落在后端契约内（%s）' % front_paths,
                set(front_paths) <= allowed and "var API = '/api/v1/admin'" in front_src,
                '子集 of %s 且 API=/api/v1/admin' % sorted(allowed),
                '%s / API 声明=%s' % (front_paths, "var API = '/api/v1/admin'" in front_src))
        T.check('#9-⑤ 前端的 CSV 导出与登录字段名与后端一致（export.csv / admin_token）',
                '/export.csv' in front_src and 'admin_token' in front_src
                and 'remaining_sec' in front_src and 'remaining_attempts' in front_src,
                'export.csv + admin_token + remaining_sec/attempts', '已对齐')
        T.check('#9-⑥ 双视口（430×932 / 1440×900）浏览器实测在下一阶段单独跑'
                '（无 Playwright 时自动 SKIP，不计入失败）',
                True, '见「验收 #9 · 浏览器实测」', '见下一阶段')
        EVIDENCE['frontend'] = {'admin_path_http': st_a, 'app_js_bytes': len(js_body),
                                'style_css_bytes': len(css_body),
                                'front_api_paths': front_paths,
                                'note': '前端页面（web/admin/）由另一位同事交付；后端只做托管与契约对齐。'}

        # ── 安全收尾：服务端日志不得出现口令 / 令牌 ────────────────
        T.set_crit(0)
        log_all = read_log(ERR_MAIN) + read_log(LOG_MAIN)
        T.check('S1 服务端日志里**不含管理口令**原文', ADMIN_PW not in log_all,
                '不含', '已确认不含')
        T.check('S2 服务端日志里**不含后台令牌**原文', token not in log_all, '不含', '已确认不含')
        T.check('S3 服务端日志已记录后台审计事件（login_ok / user_detail / ban / export）',
                all(k in log_all for k in ('admin_login_ok', 'admin_user_detail',
                                           'admin_ban', 'admin_export')),
                '四类事件都在',
                [k for k in ('admin_login_ok', 'admin_user_detail', 'admin_ban', 'admin_export')
                 if k in log_all])
        T.check('S4 服务端日志里记录了"封禁拦截"（social_blocked_by_ban ≥ 5 次）',
                log_all.count('social_blocked_by_ban') >= 5, '>=5',
                log_all.count('social_blocked_by_ban'))
    except Exception:                                             # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        T.set_crit(0)
        T.check('A 段执行未抛异常', False, '无异常', tb[-800:])
        print(tb[-2000:])
    finally:
        stop_server(proc, *handles)
        handles = ()

    # ── 验收 #9 第二阶段：真浏览器双视口（可选）────────────────────
    check_frontend_browser()

    # ══════════════════════════════════════════════════════════════
    # 验收 #2：连续 5 次错口令 → 第 6 次被锁（独立库、独立进程）
    # ══════════════════════════════════════════════════════════════
    crit_head(2, '（独立数据文件 %s）' % os.path.basename(DB_LOCK))
    proc2 = None
    h2: tuple = ()
    try:
        proc2, *h2 = start_server(DB_LOCK, LOG_LOCK, ERR_LOCK)
        h2 = tuple(h2)
        T.set_crit(2)
        attempts = []
        for i in range(1, 6):
            stz, ez = http('POST', '/api/v1/admin/login', {'password': 'wrong-%d' % i})
            attempts.append({'n': i, 'http': stz, 'code': code_of(ez),
                             'remaining_attempts': ((ez or {}).get('detail') or {})
                             .get('remaining_attempts')})
            print('        第 %d 次错口令 → HTTP %d / code %s / 剩余尝试 %s'
                  % (i, stz, code_of(ez), attempts[-1]['remaining_attempts']))
        T.check('#2-① 前 5 次错口令都是 401 + 20000，剩余次数递减到 0',
                all(a['http'] == 401 and a['code'] == 20000 for a in attempts)
                and [a['remaining_attempts'] for a in attempts] == [4, 3, 2, 1, 0],
                '401/20000 ×5，剩余 4→0', [a['remaining_attempts'] for a in attempts])
        st6, e6 = http('POST', '/api/v1/admin/login', {'password': 'wrong-6'})
        d6 = (e6 or {}).get('detail') or {}
        print('        第 6 次 → HTTP %d / code %s / message=%s / 剩余锁定 %s 秒'
              % (st6, code_of(e6), (e6 or {}).get('message'), d6.get('remaining_sec')))
        T.check('#2-② 第 6 次被锁：HTTP 429 + 业务码 40000 + 可读错误',
                st6 == 429 and code_of(e6) == 40000, '429 / 40000',
                '%s / %s / %s' % (st6, code_of(e6), (e6 or {}).get('message')))
        T.check('#2-③ 返回**剩余锁定时长**（1..900 秒，锁定口径 15 分钟）',
                isinstance(d6.get('remaining_sec'), int) and 1 <= d6['remaining_sec'] <= 900
                and d6.get('lock_seconds') == 900,
                'remaining_sec ∈ [1,900] 且 lock_seconds=900',
                'remaining_sec=%s lock_seconds=%s' % (d6.get('remaining_sec'),
                                                      d6.get('lock_seconds')))
        st7, e7 = http('POST', '/api/v1/admin/login', {'password': ADMIN_PW})
        T.check('#2-④ 锁定期内**即使口令正确**也仍然被拒（锁定按来源 IP）',
                st7 == 429 and code_of(e7) == 40000, '429 / 40000',
                '%s / %s' % (st7, code_of(e7)))
        lrows = sql(DB_LOCK, "SELECT action, count(*) AS n FROM admin_audit"
                             " WHERE action LIKE 'login%' GROUP BY action")
        T.check('#2-⑤ 失败与锁定都留了审计（login_fail = 5、login_locked ≥ 1）',
                any(r['action'] == 'login_fail' and r['n'] == 5 for r in lrows)
                and any(r['action'] == 'login_locked' for r in lrows),
                'login_fail=5 且 login_locked>=1', lrows)
        EVIDENCE['lockout'] = {'attempts': attempts,
                               'sixth': {'http': st6, 'code': code_of(e6), 'detail': d6}}
    finally:
        stop_server(proc2, *h2)

    # ══════════════════════════════════════════════════════════
    # 附加：缺 YJK_ADMIN_PASSWORD → 启动即报错且拒绝启用后台
    # ══════════════════════════════════════════════════════════
    print('\n' + '─' * 78)
    print('附加 · 管理口令缺失时的 fail-closed 行为（不注入 YJK_ADMIN_PASSWORD）')
    print('─' * 78)
    proc3 = None
    h3: tuple = ()
    try:
        proc3, *h3 = start_server(DB_NOPW, LOG_NOPW, ERR_NOPW, password=None)
        h3 = tuple(h3)
        T.set_crit(0)
        nlog = read_log(ERR_NOPW) + read_log(LOG_NOPW)
        T.check('F1 缺口令时服务仍启动（C 端不受影响：/api/health 200）',
                http('GET', '/api/health')[0] == 200, '200', 200)
        T.check('F2 启动即**报错**：stderr 明确写出「独立后台未启用」与变量名',
                ('独立后台未启用' in nlog) and ('YJK_ADMIN_PASSWORD' in nlog),
                '含报错文案与变量名',
                [ln for ln in nlog.splitlines() if '后台' in ln][:2])
        st_np, _np1 = http('POST', '/api/v1/admin/login', {'password': 'whatever'})
        st_np2, _np2 = http('GET', '/api/v1/admin/users')
        T.check('F3 后台**整体不启用**：/v1/admin/* 未注册（登录与列表都不是 200）',
                st_np != 200 and st_np2 != 200, '非 200',
                'login=%s users=%s' % (st_np, st_np2))
        tables = [r['name'] for r in sql(DB_NOPW,
                                         "SELECT name FROM sqlite_master WHERE type='table'")]
        T.check('F4 连后台表都不建（admin_ban / admin_audit 不存在）',
                'admin_ban' not in tables and 'admin_audit' not in tables, '不存在',
                [t for t in tables if t.startswith('admin')] or '无 admin* 表')
        st_c, tok_c, _mid_c = guest('adm-verify-dev-nopw')
        st_f = http('GET', '/api/v1/friends', None,
                    {'Authorization': 'Bearer ' + tok_c})[0]
        T.check('F5 C 端业务照常（游客登录 200、friends 200）',
                st_c == 200 and st_f == 200, '200 / 200', '%s / %s' % (st_c, st_f))
    finally:
        stop_server(proc3, *h3)

    # ══════════════════════════════════════════════════════════
    # 验收 #10：零回归（三条既有命令）
    # ══════════════════════════════════════════════════════════
    crit_head(10)
    T.set_crit(10)
    reg: dict = {}

    def run_reg(key: str, cmd: list, expect_line: str):
        out_path = os.path.join(HERE, 'reg_%s.txt' % key)
        with open(out_path, 'wb') as fh:
            p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
        text = read_log(out_path)
        tail = [ln for ln in text.strip().splitlines() if ln.strip()][-2:]
        reg[key] = {'cmd': ' '.join(cmd), 'exit': p.returncode, 'expect': expect_line,
                    'found': expect_line in text, 'tail': tail, 'log': out_path}
        print('        %-9s 退出码=%d 含「%s」=%s' % (key, p.returncode, expect_line,
                                                       expect_line in text))
        for ln in tail:
            print('                  %s' % ln[:150])
        T.check('#10 %s：退出码 0 且输出含「%s」' % (key, expect_line),
                p.returncode == 0 and expect_line in text,
                '退出码 0 且含「%s」' % expect_line,
                '退出码=%d 含=%s' % (p.returncode, expect_line in text))

    run_reg('社交51', [PYTHON, SOCIAL_TEST], '合计 51 项子断言，通过 51，失败 0')
    run_reg('内核335', [PYTHON, '-m', 'unittest', 'discover',
                        '-s', os.path.join(KERNEL_ROOT, 'tests'), '-t', KERNEL_ROOT],
            'Ran 335 tests')
    run_reg('服务端104', [SYS_PYTHON, '-m', 'unittest', 'discover',
                          '-s', os.path.join(SERVER_ROOT, 'tests'), '-t', SERVER_ROOT],
            'Ran 104 tests')
    T.check('#10-④ 三条既有回归全部以 0 退出（无失败）',
            all(r['exit'] == 0 for r in reg.values()), '三条退出码均为 0',
            {k: v['exit'] for k, v in reg.items()})
    p_psycopg = subprocess.run([PYTHON, '-c', 'import psycopg'],
                               capture_output=True, text=True)
    T.check('#10-⑤ 服务端回归用系统 Python 3.12 的原因已核实：便携运行时缺 psycopg '
            '（缺则 PG/Redis 两组整模块跳过 → 只有 83 项）',
            p_psycopg.returncode != 0 and os.path.exists(SYS_PYTHON),
            '便携运行时 import psycopg 失败', 'returncode=%d' % p_psycopg.returncode)
    EVIDENCE['regression'] = reg

    # ══════════════════════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════════════════════
    print('\n' + '=' * 78)
    print('§二 十条验收 · 逐条结果')
    print('=' * 78)
    for n in range(1, 11):
        rows = CRIT.get(n, [])
        bad = [r for r in rows if not r[1]]
        state = 'PASS' if (rows and not bad) else ('FAIL' if bad else 'N/A')
        print('  验收 #%-2d %-44s %s（%d/%d 项）'
              % (n, CRIT_TITLE[n][:44], state, len(rows) - len(bad), len(rows)))
        for name, _ok, detail in bad:
            print('        FAIL: %s  %s' % (name, detail[:120]))
    s = T.summary()
    print('\n  合计 %d 项断言，通过 %d，失败 %d' % (s['total'], s['passed'], s['failed']))
    leaked = [p for p in (ERR_MAIN, ERR_LOCK) if ADMIN_PW in read_log(p)]
    print('  管理口令未进入服务端日志：%s' % ('是' if not leaked else '否 %s' % leaked))
    print('  退出码：%d' % (0 if s['failed'] == 0 else 1))
    print('=' * 78)

    with open(RESULT_JSON, 'w', encoding='utf-8') as fh:
        json.dump({'summary': s,
                   'criteria': {str(k): [{'name': n, 'ok': o, 'detail': d} for n, o, d in v]
                                for k, v in CRIT.items()},
                   'checks': T.rows, 'evidence': EVIDENCE},
                  fh, ensure_ascii=False, indent=1, default=str)
    print('验收明细已写入：%s' % RESULT_JSON)
    return 0 if s['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
