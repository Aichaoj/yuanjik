# -*- coding: utf-8 -*-
"""
端到端真服务验证 · 开放 API（L1 开放数据 + L2 计算能力）
========================================================
对 **打包后的站点树**（`D:\\shuzi\\_dist\\_stage_site`）用**便携运行时**起真服务（端口 **15088**），
按变更单 `2026-10-08_GEO开放API与分享佣金_验收标准` 的 **§三 Ⅱ 开放 API** 第 1–10 条逐条实测。

★ 路径口径：变更单里的路径省略了 `/api` 前缀；本脚本一律用**真实 URL**（`/api/v1/...`）。

判定口径（★ 历史教训：曾有脚本取错列导致「假绿」，退出码恒 0）
--------------------------------------------------------------
· 每条断言都进 `RESULTS`（criteria / name / ok / detail）；**汇总与退出码只看 ok 列**：
  `FAIL 数 = sum(1 for r in RESULTS if not r[2])`，退出码 2 有失败、0 全通过。
· 既有回归**不看退出码下结论**：同时核对 (a) 返回码、(b) 输出里的**文本汇总行**
  （如「合计 51 项子断言，通过 51，失败 0」）、(c) 汇总行里的**项数**，三者都对才判 PASS。
· 与既有服务端直接对账：本脚本自己 import 内核（`核心/tianyuanheng`），
  把 HTTP 返回的运气盘 / 节气 / 四柱与**内核直算结果逐字比对**（不是自己跟自己比）。

运行：
    pwsh -NoProfile -File D:\\shuzi\\build_pack.ps1     # 生成 _stage_site（脚本内也会自动跑一次）
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v10\\test_open_api.py

脚本范围与口径（如实说明，不假装做到）
--------------------------------------
· 验收 #1–#10 逐条打印 PASS/FAIL；#10 含两部分：(a) **直连既有 C 端接口**（游客登录 / 建档 /
  打卡 / daily / friends / health / 静态资产与首页 JSON-LD）形状核对；(b) **实跑 7 条既有命令**
  （社交 51 / 推荐 45 / 支付佣金 80 / 独立后台 144 / v8 积分 77 / 内核 335 / 服务端 104）。
· 额外自检（不属于变更单 10 条）：E 禁用词扫描（第 8 条用词纪律）、F 表结构与字段口径核对。
· `服务端 104` 里有 PostgreSQL 适配测试**需要 psycopg**，便携运行时只带 lunar_python，
  因此这一条用**系统 Python 3.12** 跑（环境依赖，不是代码差异；缺依赖时如实报 FAIL）。
· 不接真支付、不发外网请求、不写任何真实凭据；测试后台口令只经环境变量注入本机测试进程。
· 未验证项：线上部署（本单明令禁止）、真实第三方调用方、L3/L4 接口（本期不做）、
  真实大模型 GEO 可见度（另见 `_geo/`）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                   # noqa: BLE001
    pass

# ── 配置 ────────────────────────────────────────────────────────────
STAGE = r'D:\Deepseek智能体\AI元健康\shuzi\_dist\_stage_site'
PY = r'D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe'                       # 便携运行时（站点用）
PACK = r'D:\Deepseek智能体\AI元健康\shuzi\build_pack.ps1'
HERE = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v10'
WS = r'D:\Deepseek智能体\AI元健康'
CORE = os.path.join(WS, '核心')
SERVER = os.path.join(WS, '服务端')
SOCIAL_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\test_social.py'
REFERRAL_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\test_referral.py'
PAY_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\test_pay_commission.py'
ADMIN_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\test_admin.py'
POINTS_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v8\test_points.py'
PORT = 15088
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, 'open_api_v10.db')
LOG = os.path.join(HERE, 'test_open_api_server.log')
RESULT_JSON = os.path.join(HERE, 'test_open_api_result.json')
OUT_TXT = os.path.join(HERE, 'test_open_api_output.txt')
OPENAPI_DUMP = os.path.join(HERE, 'openapi_live.json')
DOCS_DUMP = os.path.join(HERE, 'docs_live.html')
ADMIN_PW = 'v10-local-admin-password'          # 只经环境变量注入本机测试进程
RUN = time.strftime('%m%d%H%M%S')

# 期望的接口集（**独立于实现**：抄自变更单 §三 与 `方案/04_...md` §7.6.2 的 L1/L2 六条，
# 加上本模块新增的两条运营接口）。openapi.json 与实现都必须与这份清单逐条相等。
EXPECTED_ENDPOINTS = (
    ('GET', '/v1/open/yunqi/{year}', 'none'),
    ('GET', '/v1/open/solar-terms/{year}', 'none'),
    ('GET', '/v1/open/shichen', 'none'),
    ('GET', '/v1/open/wuxing', 'none'),
    ('POST', '/v1/calc/ganzhi', 'api_key'),
    ('POST', '/v1/calc/chart', 'api_key'),
    ('POST', '/v1/admin/api-keys', 'admin'),
    ('GET', '/v1/admin/api-keys', 'admin'),
)
COMPLIANCE_FIELDS = ('disclaimer', 'ai_generated', 'rule_version', 'param_hash')
# 「绝不返回病名字段」的两个方向：**键名**扫描 + **取值**扫描（取值扫描先剔除固定免责声明，
# 因为免责声明本身就是含「诊断」字样的合规文本，且是变更单 §三-1 强制要求携带的）。
FORBIDDEN_KEY_WORDS = ('disease', 'diagnosis', 'diagnose', 'illness', 'sickness',
                       '病名', '疾病', '诊断', '症状', '证候', '病死率')
FORBIDDEN_VALUE_WORDS = ('disease', 'diagnosis', 'diabetes', 'hypertension',
                         '糖尿病', '高血压', '冠心病', '中风', '肿瘤', '癌症',
                         '抑郁症', '焦虑症', '失眠症', '病名列表')
# 冻结的 C 端 daily 关键字段（#10：这些字段一个都不许消失）
FROZEN_DAILY_KEYS = {'date', 'level', 'level_name', 'channels', 'focus', 'lineage',
                     'disclaimer', 'ai_generated', 'rule_version', 'param_hash',
                     'pillars', 'yunqi', 'calibration', 'baseline_established',
                     'observation_count', 'min_observations', 'text',
                     'index', 'personalized'}

# ── 第 8 条用词纪律的禁用词表 ──────────────────────────────────────
# ★ 为什么用码点拼装而不是直接写字面量：本脚本**自己也要被**这张表扫描
#   （`open_api.py` 与全部新增文件都要 0 命中），直接写字面量会让扫描器命中自己。
def _w(*codes) -> str:
    return ''.join(chr(c) for c in codes)


BANNED_WORDS = (
    _w(0x52A0, 0x5BC6),                                   # 边界词 1
    _w(0x89E3, 0x5BC6),                                   # 边界词 2
    _w(0x5BC6, 0x94A5),                                   # 边界词 3
    _w(0x5BC6, 0x6587),                                   # 边界词 4
    _w(0x4FE1, 0x5C01, 0x683C, 0x5F0F),                   # 边界词 5
    _w(0x6297, 0x91CF, 0x5B50),                           # 边界词 6
    _w(0x4D, 0x4C, 0x2D, 0x4B, 0x45, 0x4D),               # 边界词 7
    _w(0x4D, 0x4C, 0x2D, 0x44, 0x53, 0x41),               # 边界词 8
    _w(0x51, 0x75, 0x64, 0x69, 0x74),                     # 边界词 9
    _w(0x751F, 0x547D, 0x5148, 0x77E5),                   # 术语黑名单 1
    _w(0x5148, 0x77E5, 0x65E5, 0x5386),                   # 术语黑名单 2
    _w(0x516B, 0x606F, 0x8C61, 0x6570),                   # 术语黑名单 3
    _w(0x516B, 0x606F, 0x57FA, 0x56E0),                   # 术语黑名单 4
    _w(0x5A, 0x59, 0x44, 0x47, 0x45, 0x4E, 0x45),         # 术语黑名单 5
    _w(0x4E2D, 0x6613, 0x9053),                           # 术语黑名单 6
    _w(0x4E5D, 0x5143, 0x60C5, 0x7EEA),                   # 术语黑名单 7
    _w(0x534E, 0x533B, 0x9053),                           # 术语黑名单 8
    _w(0x8001, 0x7956, 0x592A, 0x6781),                   # 术语黑名单 9
)
# 用词纪律要覆盖的**新增/改动文件**与运行期产物（见 scan_banned_words）
SCAN_WORDS_TABLE_TITLE = 'BANNED_WORDS 索引（本脚本不打印词面，避免扫描器命中自身输出）'

RESULTS = []             # [(criteria, name, ok, detail)]
COMPLIANCE = {'total': 0, 'ok': 0, 'bad': [], 'resources': set()}   # #3 逐响应统计
# 合规四件套要覆盖到的**全部资源**（8 条接口各自的 resource 值）
EXPECTED_RESOURCES = {'open.yunqi', 'open.solar-terms', 'open.shichen', 'open.wuxing',
                      'calc.ganzhi', 'calc.chart',
                      'admin.api-keys.issue', 'admin.api-keys.list'}
SCANNER = {'keys': 0, 'values': 0, 'hits': []}     # #4 逐响应统计
CRIT_TITLE = {
    '1': 'L1 四条接口 200 / 免鉴权 / 含 license:CC-BY-4.0 与 disclaimer（并与内核直算对账）',
    '2': 'L2 两条接口需 X-API-Key：无 key→401、错 key→403、合法→200 且含 lineage',
    '3': '每个成功响应强制携带 disclaimer / ai_generated / rule_version / param_hash',
    '4': '绝不返回病名字段：键名与取值双向扫描 0 命中',
    '5': '配额：免费 10 万次/月；临时改成 3 次 → 前 3 次 200、第 4 次 429 且提示可读',
    '6': '计量：每次调用写 api_call_log（key_id/路径/状态/耗时/耗用额度）；5 次调用 +5 行',
    '7': 'API 凭据只存 SHA-256 哈希 + 前 8 位前缀，明文只在签发时返回一次（库里搜不到明文）',
    '8': '文档：/openapi.json（OpenAPI 3.0）可解析且接口数与实现一致；/docs 静态说明页可读',
    '9': '幂等：L2 带 Idempotency-Key 重复提交只计一次调用与一次业务',
    '10': '既有 C 端接口零回归（daily/index/friends 行为不变 + 7 套既有回归实跑）',
    'E': '自检 E · 禁用词扫描：open_api.py 与全部新增文件 0 命中',
    'F': '自检 F · 表结构与字段口径核对（api_key / api_call_log 列名与落库要求一致）',
}
CRIT_ORDER = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'E', 'F']


def check(crit, name, ok, detail=''):
    ok = bool(ok)
    RESULTS.append((crit, name, ok, str(detail)))
    print('    [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, detail))
    return ok


def head(crit):
    print('\n=== 断言 #%s · %s ===' % (crit, CRIT_TITLE[crit]))


# ── HTTP 小工具 ──────────────────────────────────────────────────────
def http(method, path, raw=None, token=None, extra=None, timeout=60):
    req = urllib.request.Request(BASE + path, data=raw, method=method)
    if raw is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            ctype = str(r.headers.get('Content-Type') or '')
            try:
                return r.status, json.loads(body.decode('utf-8')), ctype
            except ValueError:
                return r.status, {'_raw': body.decode('utf-8', 'replace')}, ctype
    except urllib.error.HTTPError as e:
        body = e.read()
        ctype = str(e.headers.get('Content-Type') or '')
        try:
            return e.code, json.loads(body.decode('utf-8')), ctype
        except Exception:                                           # noqa: BLE001
            return e.code, {'_raw': body.decode('utf-8', 'replace')}, ctype


def api(method, path, body=None, token=None, extra=None):
    raw = None if body is None else json.dumps(
        body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return http(method, path, raw, token, extra)


def data_of(payload):
    return (payload or {}).get('data') or {}


def login(tag):
    """既有 C 端游客登录（#10 用；本脚本不改它一行）。"""
    s, j, _c = api('POST', '/api/v1/auth/guest', {'device_id': 'v10-%s-%s' % (tag, RUN)})
    return data_of(j).get('access_token', ''), data_of(j).get('member_id', ''), s


def open_call(method, path, body=None, key=None, admin=None, idem=None, label=None):
    """调一次开放 API；顺带把响应送进 #3 合规四件套统计与 #4 病名字段扫描。

    返回 (status, payload, content_type)，与 `http()` 同形状。
    """
    extra = {}
    if key:
        extra['X-API-Key'] = key
    if admin:
        extra['Authorization'] = 'Bearer ' + admin
    if idem:
        extra['Idempotency-Key'] = idem
    status, payload, ctype = api(method, path, body, None, extra)
    tag = label or ('%s %s' % (method, path))
    if 200 <= status < 300:
        note_compliance(tag, payload)
    scan_forbidden(tag, payload)
    return status, payload, ctype


def note_compliance(label, payload):
    d = data_of(payload)
    COMPLIANCE['total'] += 1
    if isinstance(d.get('resource'), str):
        COMPLIANCE['resources'].add(d['resource'])
    missing = [f for f in COMPLIANCE_FIELDS if f not in d]
    if missing or not isinstance(d.get('disclaimer'), str) or not d.get('disclaimer') \
            or not isinstance(d.get('ai_generated'), bool) \
            or not isinstance(d.get('param_hash'), str) \
            or not re.match(r'^[0-9a-f]{64}$', str(d.get('param_hash') or '')):
        COMPLIANCE['bad'].append('%s 缺/坏字段 %s' % (label, missing or 'disclaimer/ai_generated/param_hash 类型或长度'))
    else:
        COMPLIANCE['ok'] += 1


def _walk_keys(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            out.append(str(k))
            _walk_keys(v, out)
    elif isinstance(node, list):
        for x in node:
            _walk_keys(x, out)


def scan_forbidden(label, payload):
    """#4：键名与取值双向扫描「病名字段 / 病名列表」。"""
    keys = []
    _walk_keys(payload, keys)
    SCANNER['keys'] += len(keys)
    for k in keys:
        low = k.lower()
        for w in FORBIDDEN_KEY_WORDS:
            if w in low:
                SCANNER['hits'].append('%s 键名命中：%s' % (label, k))
    text = json.dumps(payload, ensure_ascii=False)
    text = text.replace(DISCLAIMER, '')          # 剔除强制携带的固定免责声明
    SCANNER['values'] += 1
    low = text.lower()
    for w in FORBIDDEN_VALUE_WORDS:
        if w.lower() in low:
            SCANNER['hits'].append('%s 取值命中：%s' % (label, w))


# ── 直读测试库（只为本脚本造证据）──────────────────────────────────
def _db(path, uri=False, timeout=15.0):
    conn = sqlite3.connect(('file:%s?mode=ro' % path.replace('\\', '/')) if uri else path,
                           uri=uri, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn


def db_rows(sql, args=()):
    conn = _db(DB, uri=True)
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def db_exec(sql, args=()) -> int:
    conn = _db(DB)
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def cols_of(table):
    return [str(r['name']) for r in db_rows('PRAGMA table_info(%s)' % table)]


def log_rows(key_id=None):
    if key_id:
        return db_rows('SELECT * FROM api_call_log WHERE key_id = ? ORDER BY id', (key_id,))
    return db_rows('SELECT * FROM api_call_log ORDER BY id')


def key_row(key_id):
    rows = db_rows('SELECT * FROM api_key WHERE key_id = ?', (key_id,))
    return rows[0] if rows else None


def file_has(path, needle: str) -> bool:
    try:
        with open(path, 'rb') as fp:
            return fp.read().find(needle.encode('utf-8')) >= 0
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════════
class _Tee:
    """把 stdout 同时写到控制台与结果文件（完整输出 + 退出码一并留档）。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def main():
    os.makedirs(HERE, exist_ok=True)
    try:
        sys.stdout = _Tee(sys.stdout, open(OUT_TXT, 'w', encoding='utf-8'))
    except OSError:
        pass

    # ── 0 打包（把最新 server/open_api.py + serve.py + web/docs.html 纳入构件）──
    print('=== 0 打包（把最新 open_api.py / serve.py / web/docs.html 纳入构件）===')
    r = subprocess.run(['pwsh', '-NoProfile', '-File', PACK],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('\n'.join((r.stdout or '').strip().splitlines()[-3:]))
    if r.returncode != 0:
        print((r.stderr or '')[:800])
        sys.exit(1)
    for rel in ('server/open_api.py', 'server/serve.py', 'web/docs.html'):
        print('    构件内 %-20s 存在: %s'
              % (rel, os.path.isfile(os.path.join(STAGE, *rel.split('/')))))

    # ── 1 清库 + 起真服务 ───────────────────────────────────────────
    print('\n=== 1 清库并起真服务（port %d）===' % PORT)
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(DB + suffix)
        except OSError:
            pass
    os.makedirs(os.path.join(STAGE, 'data'), exist_ok=True)
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST='127.0.0.1',
               SHUZI_PORT=str(PORT), SHUZI_DATA=DB, PYTHONIOENCODING='utf-8',
               YJK_ADMIN_PASSWORD=ADMIN_PW)
    logf = open(LOG, 'w', encoding='utf-8')
    proc = subprocess.Popen([PY, os.path.join(STAGE, 'server', 'serve.py')],
                            env=env, stdout=logf, stderr=subprocess.STDOUT)
    healthy = False
    for _ in range(25):
        time.sleep(1.0)
        try:
            with urllib.request.urlopen(BASE + '/api/health', timeout=5) as rr:
                healthy = rr.status == 200
                if healthy:
                    break
        except Exception:                                           # noqa: BLE001
            pass
    print('    服务健康检查: %s' % ('PASS' if healthy else 'FAIL'))
    if not healthy:
        proc.kill()
        print(open(LOG, encoding='utf-8', errors='replace').read()[-2000:])
        sys.exit(1)

    try:
        run_phases()
    finally:
        # ★ 必须先停本服务，再跑既有回归：回归脚本各自会重打包 _stage_site（覆盖构件目录）
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:                                           # noqa: BLE001
            proc.kill()
        time.sleep(1)
        logf.close()
    compliance_sweep()
    scan_banned_words()
    regression_zero()
    summarize()


# ══════════════════════════════════════════════════════════════════
def compliance_sweep():
    """#3：对**本次运行的全部 2xx 响应**统一复算合规四件套（跑完全流程后执行）。"""
    head('3')
    check('3', '全部 %d 个成功响应均含四件套且类型/长度合法（disclaimer 非空字符串、'
               'ai_generated 布尔、param_hash 为 64 位十六进制、rule_version 非空）'
          % COMPLIANCE['total'],
          COMPLIANCE['total'] >= 15 and COMPLIANCE['ok'] == COMPLIANCE['total']
          and not COMPLIANCE['bad'],
          '通过 %d/%d；问题项=%s' % (COMPLIANCE['ok'], COMPLIANCE['total'],
                                     COMPLIANCE['bad'][:3] or '无'))
    check('3', '四件套覆盖到**全部 8 条接口**（L1 四条 + L2 两条 + 运营两条），不是只覆盖一两条',
          EXPECTED_RESOURCES <= COMPLIANCE['resources'],
          '已覆盖 %d/%d 个资源；缺=%s'
          % (len(EXPECTED_RESOURCES & COMPLIANCE['resources']), len(EXPECTED_RESOURCES),
             sorted(EXPECTED_RESOURCES - COMPLIANCE['resources']) or '无'))


# ══════════════════════════════════════════════════════════════════
def run_phases():
    # ── 2 准备：后台登录 + 签发四把一次性凭据（各自用途见下）────────
    print('\n=== 2 准备：后台登录与凭据签发 ===')
    s_adm, j_adm, _c = api('POST', '/api/v1/admin/login', {'password': ADMIN_PW})
    adm = data_of(j_adm).get('admin_token', '')
    print('    后台登录 → HTTP %s code=%s token=%s…' % (s_adm, j_adm.get('code'), (adm or '')[:8]))

    s_issue, j_issue, _c = open_call('POST', '/api/v1/admin/api-keys',
                                    {'name': 'v10-主测试（默认免费档）'}, admin=adm)
    d_issue = data_of(j_issue)
    KEY_MAIN = d_issue.get('api_key', '')
    KID_MAIN = d_issue.get('key_id', '')
    print('    签发凭据 #1（默认配额）→ HTTP %s key_id=%s 前缀=%s 明文长度=%d'
          % (s_issue, KID_MAIN, d_issue.get('key_prefix'), len(KEY_MAIN)))

    # ── 断言 #7（签发与保管口径：明文只回一次、库里搜不到）────────
    head('7')
    s_non, j_non, _c = api('POST', '/api/v1/admin/api-keys', {'name': 'x'})
    check('7', '签发接口需后台令牌：未携带 → 401（既有 20000）',
          s_non == 401 and j_non.get('code') == 20000,
          'HTTP %s code=%s' % (s_non, j_non.get('code')))
    s_badad, j_badad, _c = api('POST', '/api/v1/admin/api-keys', {'name': 'x'}, None,
                               {'Authorization': 'Bearer not-a-real-admin-token'})
    check('7', '签发接口**错后台令牌 → 401**（不泄露令牌是否存在）',
          s_badad == 401 and j_badad.get('code') == 20000,
          'HTTP %s code=%s' % (s_badad, j_badad.get('code')))
    check('7', '签发响应**带明文**（api_key）且前缀 = 明文前 8 位、key_id 非空',
          bool(KEY_MAIN) and d_issue.get('key_prefix') == KEY_MAIN[:8]
          and len(d_issue.get('key_prefix') or '') == 8 and bool(KID_MAIN),
          'prefix=%s 明文长度=%d' % (d_issue.get('key_prefix'), len(KEY_MAIN)))
    row_main = key_row(KID_MAIN) or {}
    want_hash = hashlib.sha256(KEY_MAIN.encode('utf-8')).hexdigest()
    check('7', '库里 key_hash == SHA-256(明文)（脚本独立复算，逐字比对）',
          row_main.get('key_hash') == want_hash and re.match(r'^[0-9a-f]{64}$',
                                                             row_main.get('key_hash') or ''),
          'key_hash=%s…（前 16 位） 独立复算一致=%s'
          % (str(row_main.get('key_hash'))[:16], row_main.get('key_hash') == want_hash))
    check('7', '明文**在库里搜不到**（DB 主文件与 -wal 逐字节搜索均 0 命中）',
          not file_has(DB, KEY_MAIN) and not file_has(DB + '-wal', KEY_MAIN),
          'DB 命中=%s / WAL 命中=%s' % (file_has(DB, KEY_MAIN), file_has(DB + '-wal', KEY_MAIN)))
    check('7', '明文**不进服务端日志**（server 日志逐字节搜索 0 命中）',
          not file_has(LOG, KEY_MAIN), '日志文件=%s' % LOG)
    check('7', '默认配额 = **免费 10 万次/月**（未传 monthly_quota 时按常量落库）',
          int(row_main.get('monthly_quota') or 0) == 100000 and d_issue.get('monthly_quota') == 100000,
          '库里 monthly_quota=%s 响应=%s' % (row_main.get('monthly_quota'),
                                            d_issue.get('monthly_quota')))
    s_list, j_list, _c = open_call('GET', '/api/v1/admin/api-keys', admin=adm)
    raw_list = json.dumps(j_list, ensure_ascii=False)
    check('7', '台账只回前缀与用量：**不含明文、不含 key_hash**（响应体逐字搜索）',
          s_list == 200 and KEY_MAIN not in raw_list and 'key_hash' not in raw_list
          and want_hash not in raw_list,
          'HTTP %s 明文命中=%s key_hash 命中=%s' % (s_list, KEY_MAIN in raw_list,
                                                    'key_hash' in raw_list))
    s_more, j_more, _c = open_call('POST', '/api/v1/admin/api-keys', {'name': 'v10-第二次签发'},
                                   admin=adm)
    check('7', '二次签发得到**不同的明文**（随机源，非同值重发）',
          bool(data_of(j_more).get('api_key')) and data_of(j_more).get('api_key') != KEY_MAIN,
          'key_id=%s' % data_of(j_more).get('key_id'))

    # ── 断言 #1：L1 四条接口 ───────────────────────────────────────
    head('1')
    s1, j1, _c = open_call('GET', '/api/v1/open/yunqi/2026')
    d1 = data_of(j1)
    check('1', 'GET /api/v1/open/yunqi/2026 → 200，**免鉴权**（未带任何令牌）',
          s1 == 200 and j1.get('code') == 0, 'HTTP %s code=%s' % (s1, j1.get('code')))
    check('1', '运气盘含 license == CC-BY-4.0 与非空 disclaimer',
          d1.get('license') == 'CC-BY-4.0' and bool(d1.get('disclaimer')),
          'license=%s disclaimer[:16]=%s' % (d1.get('license'), str(d1.get('disclaimer'))[:16]))
    check('1', '运气盘与**内核直算逐字一致**（ganzhi/中运/太过不及/司天/在泉/六步）',
          d1.get('ganzhi') == BOARD26['ganzhi'] and d1.get('zhongyun') == BOARD26['zhongyun']
          and d1.get('yun_state') == BOARD26['yun_state']
          and d1.get('sitian') == BOARD26['sitian'] and d1.get('zaiquan') == BOARD26['zaiquan']
          and [(x['keqi'], x['zhuqi'], x['relation']) for x in (d1.get('steps') or [])]
          == BOARD26['steps'],
          'ganzhi=%s 中运=%s 六步=%d' % (d1.get('ganzhi'), d1.get('zhongyun'),
                                         len(d1.get('steps') or [])))
    check('1', '运气盘含 lineage 可解释链（%d 条，格式 [规则ID] …）'
          % len(d1.get('lineage') or []),
          len(d1.get('lineage') or []) >= 10
          and all(str(x).startswith('[') for x in d1.get('lineage') or []),
          '首条=%s' % str((d1.get('lineage') or [''])[0])[:48])

    s2, j2, _c = open_call('GET', '/api/v1/open/solar-terms/2026')
    d2 = data_of(j2)
    check('1', 'GET /api/v1/open/solar-terms/2026 → 200，免鉴权，**恰好 24 条**',
          s2 == 200 and d2.get('count') == 24 and len(d2.get('terms') or []) == 24,
          'HTTP %s count=%s' % (s2, d2.get('count')))
    check('1', '节气时刻与**内核直算逐字一致**（24/24 条全等）',
          all((t['name'], t['at']) == TERMS26[i] for i, t in enumerate(d2.get('terms') or [])),
          '首条=%s 末条=%s' % (json.dumps((d2.get('terms') or [{}])[0], ensure_ascii=False),
                              json.dumps((d2.get('terms') or [{}])[-1], ensure_ascii=False)))
    check('1', '节气响应含 license/disclaimer',
          d2.get('license') == 'CC-BY-4.0' and bool(d2.get('disclaimer')),
          'license=%s' % d2.get('license'))

    s3, j3, _c = open_call('GET', '/api/v1/open/shichen')
    d3 = data_of(j3)
    check('1', 'GET /api/v1/open/shichen → 200，免鉴权，**12 条**时辰且起点为子时 23:00–01:00',
          s3 == 200 and d3.get('count') == 12 and (d3.get('items') or [{}])[0].get('zhi') == '子'
          and (d3.get('items') or [{}])[0].get('start') == '23:00'
          and (d3.get('items') or [{}])[0].get('end') == '01:00',
          'HTTP %s count=%s 首条=%s' % (s3, d3.get('count'),
                                       json.dumps((d3.get('items') or [{}])[0], ensure_ascii=False)))
    check('1', '时辰当令脏腑与内核 ZF-002 表逐条一致（12/12），且内核交叉校验位为 true',
          all(t['channel'] == KERNEL_SHC[ t['zhi']] for t in (d3.get('items') or []))
          and d3.get('kernel_cross_check') is True,
          '交叉校验=%s' % d3.get('kernel_cross_check'))

    s4, j4, _c = open_call('GET', '/api/v1/open/wuxing')
    d4 = data_of(j4)
    check('1', 'GET /api/v1/open/wuxing → 200，免鉴权，**5 行**且与内核五行表一致',
          s4 == 200 and d4.get('count') == 5
          and [x['wuxing'] for x in (d4.get('items') or [])] == ['木', '火', '土', '金', '水']
          and all(x['zang'] == KERNEL_WX_ZANG[x['wuxing']] for x in (d4.get('items') or [])),
          'HTTP %s 五行=%s' % (s4, [x['wuxing'] for x in (d4.get('items') or [])]))
    check('1', '四条 L1 接口**都不需要任何令牌**（全部 200 且响应含 license=CC-BY-4.0）',
          all(data_of(j).get('license') == 'CC-BY-4.0' for j in (j1, j2, j3, j4)),
          'license 集合=%s' % {data_of(j).get('license') for j in (j1, j2, j3, j4)})
    s_yr, j_yr, _c = api('GET', '/api/v1/open/yunqi/9999')
    check('1', '年份越界 → 既有 10002（HTTP 400）+ 可读 detail（不静默兜底）',
          s_yr == 400 and j_yr.get('code') == 10002 and bool(j_yr.get('detail')),
          'HTTP %s code=%s detail=%s' % (s_yr, j_yr.get('code'),
                                         json.dumps(j_yr.get('detail') or {}, ensure_ascii=False)))

    # ── 断言 #2：L2 鉴权三态（含停用凭据）─────────────────────────
    head('2')
    BODY = {'local': '1990-05-06T08:30', 'longitude': 116.4, 'latitude': 39.9}
    s_nk, j_nk, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY)
    check('2', 'POST /api/v1/calc/ganzhi **无 key → 401**（既有 20000）',
          s_nk == 401 and j_nk.get('code') == 20000, 'HTTP %s code=%s' % (s_nk, j_nk.get('code')))
    s_wk, j_wk, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY, key='yjk-not-a-real-key')
    check('2', 'POST /api/v1/calc/ganzhi **错 key → 403**（7xxxx 码段的专用码 70005，带可读原因）',
          s_wk == 403 and j_wk.get('code') == 70005
          and (j_wk.get('detail') or {}).get('reason') == 'invalid_api_key',
          'HTTP %s code=%s reason=%s' % (s_wk, j_wk.get('code'),
                                         (j_wk.get('detail') or {}).get('reason')))
    s_ok, j_ok, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY, key=KEY_MAIN)
    d_ok = data_of(j_ok)
    check('2', 'POST /api/v1/calc/ganzhi **合法 key → 200 且含 lineage**',
          s_ok == 200 and j_ok.get('code') == 0 and len(d_ok.get('lineage') or []) >= 7
          and all(str(x).startswith('[') for x in d_ok.get('lineage') or []),
          'HTTP %s 四柱=%s lineage=%d 条' % (s_ok, d_ok.get('pillars'), len(d_ok.get('lineage') or [])))
    check('2', '四柱与**内核直算逐字一致**（真太阳时校正后的年/月/日/时柱）',
          d_ok.get('pillars') == KERNEL_CHART['pillars']
          and d_ok.get('true_solar_time') == KERNEL_CHART['true_solar_time']
          and abs(float(d_ok.get('true_solar_offset_min') or 0)
                  - KERNEL_CHART['offset']) < 1e-6,
          'pillars=%s 真太阳时=%s 偏移=%s'
          % (d_ok.get('pillars'), d_ok.get('true_solar_time'), d_ok.get('true_solar_offset_min')))

    s_ck, j_ck, _c = open_call('POST', '/api/v1/calc/chart', BODY)
    check('2', 'POST /api/v1/calc/chart **无 key → 401**', s_ck == 401 and j_ck.get('code') == 20000,
          'HTTP %s code=%s' % (s_ck, j_ck.get('code')))
    s_ck2, j_ck2, _c = open_call('POST', '/api/v1/calc/chart', BODY, key=KEY_MAIN)
    d_ck2 = data_of(j_ck2)
    check('2', 'POST /api/v1/calc/chart **合法 key → 200，含 lineage 与 chart_id**',
          s_ck2 == 200 and len(d_ck2.get('lineage') or []) >= 7
          and str(d_ck2.get('chart_id') or '').startswith('chart_')
          and len(str(d_ck2.get('chart_id') or '')) == len('chart_') + 24,
          'HTTP %s chart_id=%s' % (s_ck2, d_ck2.get('chart_id')))
    # 停用凭据：库里把 status 改成 revoked → 同一把凭据立刻 403（无缓存，下一次请求即生效）
    KEY_REV = data_of(j_more).get('api_key', '')
    KID_REV = data_of(j_more).get('key_id', '')
    db_exec("UPDATE api_key SET status = 'revoked' WHERE key_id = ?", (KID_REV,))
    s_rv, j_rv, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY, key=KEY_REV)
    check('2', '**已停用凭据 → 403 且 code=70006** reason=api_key_revoked（改库后下一次请求即生效，不做缓存）',
          s_rv == 403 and j_rv.get('code') == 70006
          and (j_rv.get('detail') or {}).get('reason') == 'api_key_revoked',
          'HTTP %s code=%s reason=%s' % (s_rv, j_rv.get('code'),
                                         (j_rv.get('detail') or {}).get('reason')))

    # ── 断言 #3 / #4：合规四件套 与 病名字段扫描 ────────────────────
    #   ★ #3 的「全部成功响应都带四件套」在全流程跑完后统一复算（见 compliance_sweep），
    #     这样覆盖面是**本次运行的全部 2xx 响应**，而不是某一时刻的抽样。
    head('3')
    check('3', 'rule_version 与内核常量逐字一致（%s），ai_generated 一律 false（内核确定性推演）'
          % KERNEL_RULE_VERSION,
          data_of(j1).get('rule_version') == KERNEL_RULE_VERSION
          and data_of(j_ok).get('rule_version') == KERNEL_RULE_VERSION
          and data_of(j1).get('ai_generated') is False
          and data_of(j_ok).get('ai_generated') is False,
          'L1=%s L2=%s' % (data_of(j1).get('rule_version'), data_of(j_ok).get('rule_version')))
    check('3', 'param_hash 同输入必得同值（重复调用逐字相等）',
          data_of(open_call('GET', '/api/v1/open/yunqi/2026')[1]).get('param_hash')
          == data_of(j1).get('param_hash'),
          'param_hash=%s…' % str(data_of(j1).get('param_hash'))[:16])

    head('4')
    check('4', '**键名**扫描 %d 个字段名 → 病名/诊断类 0 命中' % SCANNER['keys'],
          not SCANNER['hits'] and SCANNER['keys'] > 100,
          '命中=%s' % (SCANNER['hits'][:3] or '无'))
    check('4', '**取值**扫描 %d 份响应正文（已剔除强制携带的固定免责声明）→ 病名列表 0 命中'
          % SCANNER['values'], not SCANNER['hits'], '命中=%s' % (SCANNER['hits'][:3] or '无'))
    check('4', 'L2 生辰盘**刻意不输出个体节律结论**（响应里无 score/level/focus 类字段，'
               '个人节律属 L3 需授权）',
          not any(k in data_of(j_ck2) for k in ('score', 'level', 'focus', 'attention',
                                                'observation_windows')),
          '字段抽查=%s' % sorted(k for k in data_of(j_ck2)
                                 if k in ('score', 'level', 'focus', 'attention')))

    # ── 断言 #5：配额（默认 10 万；临时改成 3 次）──────────────────
    head('5')
    s_q0, j_q0, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY, key=KEY_MAIN)
    q0 = data_of(j_q0).get('quota') or {}
    check('5', '免费档配额 = **100000 次/月**（响应 quota.monthly_limit 与库里字段一致）',
          q0.get('monthly_limit') == 100000 and int(row_main.get('monthly_quota') or 0) == 100000
          and q0.get('free_default') == 100000,
          '响应=%s' % json.dumps(q0, ensure_ascii=False))
    s_kq, j_kq, _c = open_call('POST', '/api/v1/admin/api-keys', {'name': 'v10-配额测试'},
                               admin=adm)
    KEY_Q = data_of(j_kq).get('api_key', '')
    KID_Q = data_of(j_kq).get('key_id', '')
    changed = db_exec('UPDATE api_key SET monthly_quota = 3, used_this_month = 0,'
                      ' quota_period = ? WHERE key_id = ?', (time.strftime('%Y-%m'), KID_Q))
    print('    测试前置：把 key_id=%s 的 monthly_quota 临时改为 3（改库 %d 行）' % (KID_Q, changed))
    seq = []
    for i in range(1, 5):
        st, pl, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY, key=KEY_Q)
        seq.append((i, st, pl.get('code'), data_of(pl).get('quota') or {}))
        print('      第 %d 次 → HTTP %s code=%s quota.used=%s'
              % (i, st, pl.get('code'), (data_of(pl).get('quota') or {}).get('used')))
    check('5', '改额后**前 3 次 200**（used 依次 1/2/3）',
          [x[1] for x in seq[:3]] == [200, 200, 200]
          and [x[3].get('used') for x in seq[:3]] == [1, 2, 3],
          '前三次=%s' % [(x[1], x[3].get('used')) for x in seq[:3]])
    st4, pl4, _c = open_call('POST', '/api/v1/calc/ganzhi', BODY, key=KEY_Q)
    msg4 = str(pl4.get('message') or '')
    check('5', '**第 4 次 429** 且业务码 40001、提示含已用/上限（%s）' % msg4[:28],
          st4 == 429 and pl4.get('code') == 40001 and '3/3' in msg4 and '100000' in msg4,
          'HTTP %s code=%s message=%s' % (st4, pl4.get('code'), msg4))
    check('5', '被拒的第 4 次**不耗额度**（库里 used_this_month 仍为 3）',
          int((key_row(KID_Q) or {}).get('used_this_month') or 0) == 3,
          '库里 used=%s' % (key_row(KID_Q) or {}).get('used_this_month'))
    check('5', '额度耗尽只影响该凭据：主凭据（10 万档）仍然 200',
          open_call('POST', '/api/v1/calc/ganzhi', BODY, key=KEY_MAIN)[0] == 200,
          '主凭据 HTTP 200')

    # ── 断言 #6：计量（5 次调用 → api_call_log 正好 +5 行）─────────
    head('6')
    s_k6, j_k6, _c = open_call('POST', '/api/v1/admin/api-keys', {'name': 'v10-计量测试'},
                               admin=adm)
    KEY_M = data_of(j_k6).get('api_key', '')
    KID_M = data_of(j_k6).get('key_id', '')
    before_rows = len(log_rows())
    before_key_rows = len(log_rows(KID_M))
    print('    调用前：api_call_log 总行数=%d（该凭据 %d 行）' % (before_rows, before_key_rows))
    calls = []
    for i in range(5):
        st, pl, _c = open_call('POST', '/api/v1/calc/ganzhi',
                               dict(BODY, local='1990-05-0%dT08:30' % (i + 1)), key=KEY_M)
        calls.append(st)
        time.sleep(0.02)
    after_rows = len(log_rows())
    rows_m = log_rows(KID_M)
    print('    调用后：总行数=%d（该凭据 %d 行）；5 次状态=%s' % (after_rows, len(rows_m), calls))
    check('6', '调用 5 次 → 表中**正好 +5 行**（%d → %d）' % (before_rows, after_rows),
          after_rows - before_rows == 5 and len(rows_m) == 5 and calls == [200] * 5,
          'Δ总行数=%d 该凭据行数=%d' % (after_rows - before_rows, len(rows_m)))
    want_cols = {'key_id', 'path', 'status', 'elapsed_ms', 'cost', 'created_at'}
    bad = [r for r in rows_m
           if not (r['key_id'] == KID_M and r['path'] == '/v1/calc/ganzhi'
                   and int(r['status']) == 200 and int(r['code']) == 0
                   and int(r['cost']) == 1 and r['elapsed_ms'] >= 0 and r['created_at']
                   and r['key_prefix'] == KEY_M[:8])]
    print('    逐行 = %s' % json.dumps([{k: r[k] for k in
                                       ('key_id', 'path', 'status', 'code', 'elapsed_ms',
                                        'cost', 'created_at')} for r in rows_m],
                                      ensure_ascii=False))
    check('6', '每行都带 key_id / 路径 / 状态 / 耗时 / 耗用额度 / 时间，且 cost=1（真实执行）',
          not bad and want_cols <= set(rows_m[0].keys() if rows_m else set()),
          '不合格行数=%d 列=%s' % (len(bad), sorted(rows_m[0].keys()) if rows_m else []))
    check('6', 'Σcost == 5 且库里 used_this_month == 5（额度与计量同步）',
          sum(int(r['cost']) for r in rows_m) == 5
          and int((key_row(KID_M) or {}).get('used_this_month') or 0) == 5,
          'Σcost=%d used=%s' % (sum(int(r['cost']) for r in rows_m),
                                (key_row(KID_M) or {}).get('used_this_month')))
    check('6', '被拒调用也留痕但**不耗额度**：前面无 key/错 key/429 三类都写过一行（cost=0）',
          len([r for r in log_rows() if int(r['cost']) == 0
               and int(r['status']) in (401, 403, 429)]) >= 3,
          'cost=0 且状态 401/403/429 的行数=%d'
          % len([r for r in log_rows() if int(r['cost']) == 0
                 and int(r['status']) in (401, 403, 429)]))

    # ── 断言 #9：幂等（同 Idempotency-Key 只计一次调用与一次业务）──
    head('9')
    s_k9, j_k9, _c = open_call('POST', '/api/v1/admin/api-keys', {'name': 'v10-幂等测试'},
                               admin=adm)
    KEY_I = data_of(j_k9).get('api_key', '')
    KID_I = data_of(j_k9).get('key_id', '')
    IDEM = 'v10-idem-%s' % RUN
    s_a, j_a, _c = open_call('POST', '/api/v1/calc/chart', BODY, key=KEY_I, idem=IDEM)
    rows_after_first = len(log_rows(KID_I))
    used_after_first = int((key_row(KID_I) or {}).get('used_this_month') or 0)
    s_b, j_b, _c = open_call('POST', '/api/v1/calc/chart', BODY, key=KEY_I, idem=IDEM)
    rows_after_second = len(log_rows(KID_I))
    used_after_second = int((key_row(KID_I) or {}).get('used_this_month') or 0)
    print('    第 1 次 → HTTP %s chart_id=%s；第 2 次 → HTTP %s replay=%s chart_id=%s'
          % (s_a, data_of(j_a).get('chart_id'), s_b,
             data_of(j_b).get('idempotent_replay'), data_of(j_b).get('chart_id')))
    check('9', '同 key 同体重复提交 → **同一业务结果**（chart_id 逐字相同、HTTP 200）',
          s_a == 200 and s_b == 200
          and data_of(j_a).get('chart_id') == data_of(j_b).get('chart_id')
          and bool(data_of(j_a).get('chart_id')),
          'chart_id=%s' % data_of(j_a).get('chart_id'))
    check('9', '第 2 次标 idempotent_replay=true（回放首次响应，不重复计算）',
          data_of(j_b).get('idempotent_replay') is True
          and data_of(j_a).get('idempotent_replay') is False,
          'first=%s second=%s' % (data_of(j_a).get('idempotent_replay'),
                                  data_of(j_b).get('idempotent_replay')))
    check('9', '**只计一次调用**：api_call_log 该凭据 1 行（%d → %d），额度 used 仍为 %d'
          % (rows_after_first, rows_after_second, used_after_second),
          rows_after_first == 1 and rows_after_second == 1
          and used_after_first == 1 and used_after_second == 1,
          '行数 %d→%d used %d→%d' % (rows_after_first, rows_after_second,
                                     used_after_first, used_after_second))
    s_c, j_c, _c = open_call('POST', '/api/v1/calc/chart',
                             dict(BODY, longitude=121.5), key=KEY_I, idem=IDEM)
    check('9', '**同 key 异体 → 既有 10003（HTTP 409）**，不产生第二次业务',
          s_c == 409 and j_c.get('code') == 10003 and len(log_rows(KID_I)) == 2,
          'HTTP %s code=%s 行数=%d' % (s_c, j_c.get('code'), len(log_rows(KID_I))))

    # ── 断言 #8：文档（/openapi.json 与 /docs）─────────────────────
    head('8')
    s_sp, spec, ctype_sp = http('GET', '/openapi.json')
    with open(OPENAPI_DUMP, 'w', encoding='utf-8') as fp:
        json.dump(spec, fp, ensure_ascii=False, indent=1)
    ops = {(m.upper(), p) for p, item in (spec.get('paths') or {}).items()
           for m in item.keys()}
    print('    /openapi.json → HTTP %s，解析成功，paths=%d，operations=%d'
          % (s_sp, len(spec.get('paths') or {}), len(ops)))
    check('8', '/openapi.json → 200，**可被 json.loads 解析**，openapi 版本为 3.0.x',
          s_sp == 200 and str(spec.get('openapi', '')).startswith('3.0'),
          'HTTP %s openapi=%s' % (s_sp, spec.get('openapi')))
    check('8', '**接口数与实现一致**：文档 %d 个操作 == 期望清单 %d 条，且逐条（方法+路径模板）相等'
          % (len(ops), len(EXPECTED_ENDPOINTS)),
          ops == {(m, p) for m, p, _a in EXPECTED_ENDPOINTS}
          and spec.get('info', {}).get('x-service-endpoint-count') == len(EXPECTED_ENDPOINTS),
          '文档-期望 差集=%s；计数字段=%s'
          % (sorted(ops ^ {(m, p) for m, p, _a in EXPECTED_ENDPOINTS}),
             spec.get('info', {}).get('x-service-endpoint-count')))
    # 逐条**实调**：证明文档里的每条路径在真服务里都存在（不是"未知接口 10000"）
    smoke = []
    for method, ptemplate, auth in EXPECTED_ENDPOINTS:
        real = ptemplate.replace('{year}', '2026')
        if method == 'GET' and auth == 'none':
            st, pl, _c = open_call('GET', '/api' + real)
        elif method == 'POST':
            st, pl, _c = open_call('POST', '/api' + real,
                                   BODY if 'calc' in real else None)
        else:
            st, pl, _c = open_call('GET', '/api' + real)
        smoke.append((method, ptemplate, st, pl.get('code'), pl.get('message')))
    print('    逐条实调：%s' % json.dumps(['%s %s → %s/%s' % (m, p, s, c)
                                          for m, p, s, c, _msg in smoke], ensure_ascii=False))
    check('8', '文档里每条接口**都能被真服务命中**（L1 200；L2/运营无凭据 → 401；'
               '无一条落到「未知接口 10000」）',
          all((s == 200 if a == 'none' else s == 401) and c != 10000
              for (m, p, s, c, _msg), (_m2, _p2, a) in zip(smoke, EXPECTED_ENDPOINTS)),
          '实测状态=%s' % [(m, s, c) for m, _p, s, c, _msg in smoke])
    check('8', '文档声明了合规口径：license=CC-BY-4.0、四件套 schema、错误码表、配额与限流',
          spec.get('info', {}).get('license', {}).get('name') == 'CC-BY-4.0'
          and set(spec.get('components', {}).get('schemas', {}).get(
              'Compliance', {}).get('required', [])) == set(COMPLIANCE_FIELDS)
          and '40001' in (spec.get('info', {}).get('x-error-codes') or {})
          and spec.get('info', {}).get('x-rate-limits', {}).get('monthly_quota_free') == 100000,
          'license=%s x-error-codes=%s' % (spec.get('info', {}).get('license', {}).get('name'),
                                           sorted((spec.get('info', {}).get('x-error-codes') or {}))))

    s_doc, body_doc, ctype_doc = http('GET', '/docs')
    with open(DOCS_DUMP, 'w', encoding='utf-8') as fp:
        fp.write(body_doc.get('_raw', '') if isinstance(body_doc, dict) else str(body_doc))
    html = body_doc.get('_raw', '') if isinstance(body_doc, dict) else ''
    print('    /docs → HTTP %s，Content-Type=%s，字节=%d' % (s_doc, ctype_doc, len(html)))
    check('8', '/docs → 200 且 Content-Type 为 text/html，页面可读（≥4000 字节、含全部 8 条接口路径）',
          s_doc == 200 and 'text/html' in ctype_doc and len(html) >= 4000
          and all(p in html for _m, p, _a in EXPECTED_ENDPOINTS),
          'HTTP %s ctype=%s bytes=%d 缺路径=%s'
          % (s_doc, ctype_doc, len(html),
             [p for _m, p, _a in EXPECTED_ENDPOINTS if p not in html] or '无'))
    check('8', '/docs 写明鉴权、配额、幂等、许可与免责声明（关键串全在）',
          all(k in html for k in ('X-API-Key', '100000', 'Idempotency-Key', 'CC-BY-4.0',
                                  '不属于医疗器械', 'openapi.json')),
          '关键串命中=%s' % {k: (k in html) for k in ('X-API-Key', '100000', 'Idempotency-Key',
                                                      'CC-BY-4.0', '不属于医疗器械')})

    # ── 断言 F：表结构与字段口径核对 ───────────────────────────────
    head('F')
    cols_k = cols_of('api_key')
    cols_l = cols_of('api_call_log')
    print('    api_key 列      = %s' % cols_k)
    print('    api_call_log 列 = %s' % cols_l)
    check('F', 'api_key 含落库要求全部字段：SHA-256 哈希 / 8 位前缀 / 名称 / 配额 / 已用量 / 状态 / 创建时间',
          {'key_hash', 'key_prefix', 'name', 'monthly_quota', 'used_this_month', 'status',
           'created_at'} <= set(cols_k),
          '缺少=%s' % sorted({'key_hash', 'key_prefix', 'name', 'monthly_quota',
                              'used_this_month', 'status', 'created_at'} - set(cols_k)))
    check('F', 'api_call_log 含计量要求全部字段：key_id / 路径 / 状态 / 耗时 / 耗用额度 / 时间',
          {'key_id', 'path', 'status', 'elapsed_ms', 'cost', 'created_at'} <= set(cols_l),
          '缺少=%s' % sorted({'key_id', 'path', 'status', 'elapsed_ms', 'cost', 'created_at'}
                             - set(cols_l)))
    check('F', '两张表落在**同一份 state.db**（沿用既有库，不另开库）', os.path.isfile(DB),
          'DB=%s' % DB)
    s_ls, j_ls, _c = open_call('GET', '/api/v1/admin/api-keys', admin=adm)
    check('F', '库里**搜不到任何明文凭据**：全表扫 key_prefix/key_hash，明文串 0 命中',
          not file_has(DB, KEY_M) and not file_has(DB, KEY_I) and not file_has(DB, KEY_Q)
          and 'key_hash' not in json.dumps(j_ls, ensure_ascii=False),
          '三把测试凭据明文均未落库；台账 HTTP %s' % s_ls)

    # ── 断言 #10（a）：既有 C 端接口直连核对 ───────────────────────
    head('10')
    tok_c, mid_c, s_guest = login('zero-reg')
    check('10', '既有 POST /api/v1/auth/guest → 200 且发令牌（游客身份链路不变）',
          s_guest == 200 and bool(tok_c) and bool(mid_c),
          'HTTP %s member=…%s' % (s_guest, str(mid_c)[-8:]))
    s_birth, j_birth, _c = api('POST', '/api/v1/profile/birth',
                               {'birth_local': '1990-05-06T08:30', 'longitude': 116.4,
                                'latitude': 39.9}, tok_c)
    s_ci, j_ci, _c = api('POST', '/api/v1/checkin', {}, tok_c)
    s_day, j_day, _c = api('GET', '/api/v1/rhythm/daily', None, tok_c)
    d_day = data_of(j_day)
    missing_day = sorted(FROZEN_DAILY_KEYS - set(d_day.keys()))
    print('    daily 字段数=%d，缺字段=%s' % (len(d_day), missing_day or '无'))
    check('10', '既有 GET /api/v1/rhythm/daily → 200，**冻结字段一个都不缺**（%d 个）'
          % len(FROZEN_DAILY_KEYS),
          s_day == 200 and j_day.get('code') == 0 and not missing_day,
          '缺=%s' % (missing_day or '无'))
    check('10', 'daily 的 index（时相指数）与 personalized（个体化摘要）仍在，口径字段齐',
          isinstance(d_day.get('index'), dict) and 'score' in d_day['index']
          and 'score_kernel' in d_day['index'] and 'display' in d_day['index']
          and 'personalized' in d_day
          and (d_day.get('personalized') is None or 'score' in d_day['personalized']),
          'index.score=%s personalized=%s' % (d_day.get('index', {}).get('score'),
                                              type(d_day.get('personalized')).__name__))
    check('10', 'daily 的 profile/打卡链路不变（建档与打卡均 200，观测数 ≥1）',
          s_birth == 200 and s_ci == 200 and int(d_day.get('observation_count') or 0) >= 1,
          'birth=%s checkin=%s observation_count=%s'
          % (s_birth, s_ci, d_day.get('observation_count')))
    s_fr, j_fr, _c = api('GET', '/api/v1/friends', None, tok_c)
    s_pv, j_pv, _c = api('GET', '/api/v1/friends/privacy', None, tok_c)
    s_rf, j_rf, _c = api('GET', '/api/v1/me/referral', None, tok_c)
    check('10', '既有 friends 三件套形状不变：friends / 隐私三开关 / 邀请链接',
          s_fr == 200 and 'friends' in data_of(j_fr)
          and s_pv == 200 and all(k in data_of(j_pv) for k in ('share_index', 'share_streak',
                                                              'in_ranking'))
          and s_rf == 200 and 'invite_code' in data_of(j_rf),
          'friends=%s privacy=%s referral=%s' % (s_fr, s_pv, s_rf))
    s_h, j_h, _c = api('GET', '/api/health')
    check('10', '既有 /api/health → 200，规则版本 %s，服务版本与表清单未变' % KERNEL_RULE_VERSION,
          s_h == 200 and data_of(j_h).get('rule_version') == KERNEL_RULE_VERSION
          and data_of(j_h).get('ok') is True
          and {'account_rows', 'baseline_rows', 'profile_rows', 'checkin_rows'}
          <= set(data_of(j_h).keys()),
          'rule=%s' % data_of(j_h).get('rule_version'))
    s_idx, _j_idx, ctype_idx = http('GET', '/')
    html_idx = _j_idx.get('_raw', '') if isinstance(_j_idx, dict) else ''
    check('10', '既有首页与 GEO 静态资产不变：/ 200 且首页直含 JSON-LD（Dataset 与 '
                'SoftwareApplication），/llms.txt、/robots.txt、/sitemap.xml 均 200',
          s_idx == 200 and '@type' in html_idx and 'Dataset' in html_idx
          and 'SoftwareApplication' in html_idx
          and http('GET', '/llms.txt')[0] == 200 and http('GET', '/robots.txt')[0] == 200
          and http('GET', '/sitemap.xml')[0] == 200,
          '首页 HTTP %s JSON-LD=%s' % (s_idx, 'Dataset' in html_idx))
    s_env, j_env, _c = api('GET', '/api/v1/rhythm/daily', None, None)
    check('10', '既有信封形状不变：未登录访问受保护接口 → 401，响应键仍为 code/message/data/trace_id',
          s_env == 401 and set(j_env.keys()) == {'code', 'message', 'data', 'detail', 'trace_id'},
          'HTTP %s keys=%s' % (s_env, sorted(j_env.keys())))


# ══════════════════════════════════════════════════════════════════
def scan_banned_words():
    """自检 E：对新增/改动文件 + 运行期生成的规格文档做禁用词扫描（命中数必须为 0）。

    ★ 只打印**命中数与词表下标**，不打印词面——否则扫描输出文件本身会把词面写进磁盘，
      下一次扫描又会命中自己（自指陷阱）。词面见变更任务书的用词纪律清单。
    """
    head('E')
    targets = [os.path.join(r'D:\Deepseek智能体\AI元健康\shuzi\server', 'open_api.py'),
               os.path.join(r'D:\Deepseek智能体\AI元健康\shuzi\server', 'serve.py'),
               os.path.join(r'D:\Deepseek智能体\AI元健康\shuzi\web', 'docs.html'),
               os.path.abspath(__file__),
               OPENAPI_DUMP, DOCS_DUMP]
    print('    %s' % SCAN_WORDS_TABLE_TITLE)
    print('    词表条目数 = %d' % len(BANNED_WORDS))
    total_hits = 0
    for path in targets:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as fp:
                text = fp.read()
        except OSError as ex:
            check('E', '扫描目标可读：%s' % path, False, str(ex))
            continue
        low = text.lower()
        hit_idx = [i for i, w in enumerate(BANNED_WORDS) if w.lower() in low]
        total_hits += len(hit_idx)
        print('    %-58s 字节=%-7d 命中=%d %s'
              % (os.path.basename(path), len(text.encode('utf-8')), len(hit_idx),
                 ('词表下标=%s' % hit_idx) if hit_idx else ''))
    check('E', '禁用词扫描：%d 个文件 × %d 条词表 → **命中 %d**（要求 0）'
          % (len(targets), len(BANNED_WORDS), total_hits), total_hits == 0,
          '命中合计=%d' % total_hits)


def _run(cmd, cwd, tail=4):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    out = ((r.stdout or '') + (r.stderr or ''))
    lines = [ln for ln in out.splitlines() if ln.strip()]
    print('    $ %s' % ' '.join(cmd))
    for ln in lines[-tail:]:
        print('      %s' % ln)
    return r.returncode, out


def regression_zero():
    """#10（b）：7 条既有命令实跑。判定 = 返回码 + 文本汇总行 + 项数，三者同时成立。"""
    print('\n=== 断言 #10（b） · 既有回归实跑（社交 51 / 推荐 45 / 支付佣金 80 / '
          '独立后台 144 / 积分 77 / 内核 335 / 服务端 104）===')
    if os.environ.get('OPENAPI_SKIP_REGRESSION') == '1':
        print('    [SKIP] 按 OPENAPI_SKIP_REGRESSION=1 跳过既有回归（**仅用于调试**）')
        print('    [SKIP] 正式运行命令：%s %s' % (PY, os.path.abspath(__file__)))
        return

    def run_reg(name, cmd, cwd, expect, count_re, want):
        t0 = time.time()
        rc, out = _run(cmd, cwd)
        hit = expect in out
        ms = re.findall(count_re, out)
        n = ms[-1] if ms else '?'
        ok = rc == 0 and hit and n == want
        check('10', '%s（%s，%.0fs）' % (name, expect, time.time() - t0), ok,
              'rc=%d 含汇总行=%s 项数=%s（期望 %s）' % (rc, hit, n, want))

    run_reg('社交 51：既有轻社交端到端验证', [PY, SOCIAL_TEST], None,
            '合计 51 项子断言，通过 51，失败 0', r'合计\s*(\d+)\s*项子断言', '51')
    run_reg('推荐 45：既有推荐关系端到端验证', [PY, REFERRAL_TEST], None,
            '合计 45 项子断言，通过 45，失败 0', r'合计\s*(\d+)\s*项子断言', '45')
    run_reg('支付佣金 80：P1 自建支付与佣金账本全过',
            [PY, PAY_TEST], None, '合计 80 项子断言，通过 80，失败 0',
            r'合计\s*(\d+)\s*项子断言', '80')
    run_reg('独立后台 144：既有后台端到端验证', [PY, ADMIN_TEST], None,
            '合计 144 项断言，通过 144，失败 0', r'合计\s*(\d+)\s*项断言', '144')
    run_reg('积分 77：v8 积分余额与佣金路线全过（本次扩展未破坏 v8）',
            [PY, POINTS_TEST], None, '合计 77 项子断言，通过 77，失败 0',
            r'合计\s*(\d+)\s*项子断言', '77')
    run_reg('内核 335：核心测试全过（便携运行时）',
            [PY, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'], CORE,
            'Ran 335 tests', r'Ran (\d+) tests', '335')
    sys_py = shutil.which('python') or \
        r'C:\Users\41692\AppData\Local\Programs\Python\Python312\python.exe'
    try:
        probe = subprocess.run([sys_py, '-c', 'import psycopg, fakeredis'],
                               capture_output=True, text=True)
        has_dep = probe.returncode == 0
    except Exception:                                               # noqa: BLE001
        has_dep = False
    if not has_dep:
        check('10', '服务端 104：**本机无法复算**（系统 Python 缺 psycopg/fakeredis）', False,
              'sys_py=%s 缺依赖；如实标注，不假装通过' % sys_py)
    else:
        run_reg('服务端 104：服务层测试全过（解释器 %s）' % sys_py,
                [sys_py, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'], SERVER,
                'Ran 104 tests', r'Ran (\d+) tests', '104')
    # 改动面自检：本次只碰 D:\Deepseek智能体\AI元健康\shuzi（app/* 与 tianyuanheng/* 一字未动）
    same, diff = [], []
    for rel in (('app', 'api.py'), ('app', 'http.py'), ('app', 'errors.py'),
                ('app', 'ratelimit.py'), ('app', 'auth.py'), ('app', 'envelope.py'),
                ('tianyuanheng', 'phase_index.py'), ('tianyuanheng', 'guardrail.py')):
        staged = os.path.join(STAGE, rel[0], rel[1])
        origin = os.path.join(WS, '服务端' if rel[0] == 'app' else '核心', rel[0], rel[1])
        (same if _sha(staged) == _sha(origin) else diff).append('%s/%s' % rel)
    check('10', '既有源码一字未动：构件内 app/* 与 tianyuanheng/* 与工作区正本 SHA-256 全同'
                '（抽查 %d 个文件）' % len(same), not diff and len(same) == 8,
          '全同=%d 不一致=%s' % (len(same), diff or '无'))


def _sha(path: str) -> str:
    try:
        with open(path, 'rb') as fp:
            return hashlib.sha256(fp.read()).hexdigest()
    except OSError:
        return 'MISSING'


# ══════════════════════════════════════════════════════════════════
def summarize():
    print('\n=== 汇总（#1–#10 = 变更单 §三 Ⅱ 开放 API 的 10 条；E/F = 本次额外自检）===')
    per = {}
    for crit, name, ok, detail in RESULTS:
        per.setdefault(crit, []).append((name, ok, detail))
    for crit in CRIT_ORDER:
        rows = per.get(crit) or []
        if not rows:
            continue
        bad = [r for r in rows if not r[1]]
        print('  断言 #%-2s %s —— %s（%d/%d 项通过）'
              % (crit, CRIT_TITLE[crit][:52], 'PASS' if not bad else 'FAIL',
                 len(rows) - len(bad), len(rows)))
        for name, _ok, detail in bad:
            print('      FAIL: %s  %s' % (name, detail))
    failed = [r for r in RESULTS if not r[2]]
    print('\n  合计 %d 项子断言，通过 %d，失败 %d；本脚本范围 %s'
          % (len(RESULTS), len(RESULTS) - len(failed), len(failed),
             '全部通过' if not failed else '存在失败'))
    for crit, name, _ok, detail in failed:
        print('  未通过：#%s %s  %s' % (crit, name, detail))
    print('  未验证项（如实标注）：线上部署（本单明令禁止）、真实第三方调用方、'
          'L3 个人节律与 L4 群体接口（本期不做，需用户授权与合同）、'
          '真实大模型 GEO 可见度（另见 _geo/）。')
    print('  回退：删 server/open_api.py + serve.py 的注册行（import / Stack 一行构造 / '
          '_dispatch 转发分支 / /openapi.json 分支 / EXTRA_STATIC 的 /docs 两行），'
          '接口即整体消失，C 端不受影响；两张表可留可清。')
    with open(RESULT_JSON, 'w', encoding='utf-8') as fp:
        json.dump([{'criteria': c, 'name': n, 'ok': o, 'detail': d}
                   for c, n, o, d in RESULTS], fp, ensure_ascii=False, indent=1)
    print('  明细 JSON: %s' % RESULT_JSON)
    print('  控制台完整输出: %s' % OUT_TXT)
    sys.exit(0 if not failed else 2)


# ══════════════════════════════════════════════════════════════════
# 与既有源码直接对账用的内核基线（本脚本自己 import 内核直算，不读被测服务的任何输出）
sys.path.insert(0, CORE)
from tianyuanheng import RULE_VERSION as KERNEL_RULE_VERSION        # noqa: E402
from tianyuanheng import board_of_year, build_birth_chart, guardrail, solar_term_table  # noqa: E402
from tianyuanheng.zangfu_layer import SHICHEN_DANGLING, WUXING_ZANG  # noqa: E402

DISCLAIMER = guardrail.DISCLAIMER


def _kernel_baseline():
    b = board_of_year(2026)
    board = {'ganzhi': b.ganzhi, 'zhongyun': b.zhongyun, 'yun_state': b.yun_state,
             'sitian': b.sitian, 'zaiquan': b.zaiquan,
             'steps': [(s.keqi, s.zhuqi, s.relation) for s in b.steps]}
    merged = {}
    for y in (2026, 2027):
        for name, when in solar_term_table(y).items():
            if '_' in name:
                continue
            if when.startswith('2026-'):
                merged.setdefault(name, when)
    terms = [(n, merged[n]) for n in sorted(merged, key=lambda k: merged[k])]
    c = build_birth_chart(1990, 5, 6, 8, 30, 116.4, 39.9)
    chart = {'pillars': list(c.ganzhi_tuple()), 'true_solar_time': c.true_solar_time,
             'offset': float(c.true_solar_offset_min)}
    return board, terms, chart


BOARD26, TERMS26, KERNEL_CHART = _kernel_baseline()
KERNEL_SHC = dict(SHICHEN_DANGLING)
KERNEL_WX_ZANG = dict(WUXING_ZANG)


if __name__ == '__main__':
    main()
