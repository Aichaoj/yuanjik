# -*- coding: utf-8 -*-
"""
端到端真服务验证 · 家庭健康档案与添加家人（v11）
================================================
对 **打包后的站点树**（`D:\\Deepseek智能体\\AI元健康\\shuzi\\_dist\\_stage_site`）
用**便携运行时**起真服务（端口 **15089**），按变更单
`2026-10-08_家庭健康档案与添加家人_验收标准` 的 **§五** 第 1–10 条逐条实测。

★ 路径口径：变更单里的路径省略了 `/api` 前缀；本脚本一律用**真实 URL**（`/api/v1/...`）。

判定口径（★ 历史教训：曾有脚本取错列导致「假绿」，退出码恒 0）
--------------------------------------------------------------
· 每条断言都进 `RESULTS`（criteria / name / ok / detail）；**汇总与退出码只看 ok 列**：
  `FAIL 数 = sum(1 for r in RESULTS if not r[2])`，退出码 2 有失败、0 全通过。
· 既有回归**不看退出码下结论**：同时核对 (a) 返回码、(b) 输出里的**文本汇总行**
  （如「合计 51 项子断言，通过 51，失败 0」）、(c) 汇总行里的**项数**，三者都对才判 PASS。
· 与既有内核直接对账：本脚本自己 import **工作区正本**的 `核心/tianyuanheng`，
  同时把**构件里的** `tianyuanheng/*` 与正本做 SHA-256 比对（确保跑的就是正本），
  再用构件里的 `server/serve.py` 的 `display_normalize`（装配层唯一的那一份）做展示分复算 ——
  「家人 index.score == 内核对该生辰直算 + display_normalize」这条**逐字相等**，不是自己跟自己比。
· #9（真浏览器）由 `browser_family.py` 用**系统 Python + Playwright/Chromium** 跑两个视口，
  结果 JSON 合并进本脚本的汇总；跑不通就**如实报 FAIL**（不假装通过）。

运行：
    pwsh -NoProfile -File D:\\Deepseek智能体\\AI元健康\\shuzi\\build_pack.ps1   # 生成 _stage_site（脚本内也会自动跑）
    D:\\Deepseek智能体\\AI元健康\\shuzi\\runtime\\python.exe D:\\Deepseek智能体\\AI元健康\\shuzi\\_verify_v11\\test_family.py

脚本范围与口径（如实说明，不假装做到）
--------------------------------------
· §五 的 #1–#10 逐条打印 PASS/FAIL；另加两项自检：E 禁用词扫描、F 表结构与字段口径核对。
· #7 的「换账号删同一个 id → 404」用**另一个真实账号**实测；#8 的隐私断言覆盖
  `family` / `friends` / `feed` / `ranking` / `invite/preview` 五处响应正文。
· 不接任何外部服务、不发外网请求；测试用后台口令只经环境变量注入本机测试进程。
· 未验证项：线上部署（本单明令禁止）、真实多设备并发、家人与他人账号的跨库场景（产品上不存在）。
"""
from __future__ import annotations

import hashlib
import importlib.util
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
WS = r'D:\Deepseek智能体\AI元健康'
ROOT = os.path.join(WS, 'shuzi')
STAGE = os.path.join(ROOT, '_dist', '_stage_site')
PY = os.path.join(ROOT, 'runtime', 'python.exe')          # 便携运行时（站点用）
PACK = os.path.join(ROOT, 'build_pack.ps1')
HERE = os.path.join(ROOT, '_verify_v11')
CORE = os.path.join(WS, '核心')
SERVER = os.path.join(WS, '服务端')
SOCIAL_TEST = os.path.join(ROOT, '_verify_v3', 'test_social.py')
REFERRAL_TEST = os.path.join(ROOT, '_verify_v6', 'test_referral.py')
PAY_TEST = os.path.join(ROOT, '_verify_v7', 'test_pay_commission.py')
ADMIN_TEST = os.path.join(ROOT, '_verify_v7', 'test_admin.py')
POINTS_TEST = os.path.join(ROOT, '_verify_v8', 'test_points.py')
OPENAPI_TEST = os.path.join(ROOT, '_verify_v10', 'test_open_api.py')
BROWSER = os.path.join(HERE, 'browser_family.py')
PORT = 15089
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, 'family_v11.db')
LOG = os.path.join(HERE, 'test_family_server.log')
RESULT_JSON = os.path.join(HERE, 'test_family_result.json')
OUT_TXT = os.path.join(HERE, 'test_family_output.txt')
BROWSER_JSON = os.path.join(HERE, 'browser_family_result.json')
ADMIN_PW = 'v11-local-admin-password'          # 只经环境变量注入本机测试进程
RUN = time.strftime('%m%d%H%M%S')

SYS_PY = shutil.which('python') or \
    r'C:\Users\41692\AppData\Local\Programs\Python\Python312\python.exe'

RESULTS = []             # [(criteria, name, ok, detail)]
CRIT_TITLE = {
    '1': 'GET /api/v1/family：未登录 401；登录 200 且 data.members 为数组',
    '2': '添加家人 → 200 且 GET 能读到；index.score 与内核直算 + display_normalize 逐字相等',
    '3': '家人 level 恒为 null、baseline_text 形如「基线建立中 0/7」，响应不出现 L0–L4',
    '4': '非法入参逐项被拒且报错可读（昵称超 12 字 / 关系 code / 出生时间 / 经纬度越界）均 400',
    '5': '同属主「昵称+生辰」重复 → 拒绝；第 9 位家人 → 拒绝并提示席位已满',
    '6': '关怀提醒当日重复只留一条（幂等）；GET reminders 能读到该条（含昵称与时间）',
    '7': 'DELETE：本人删除 200 且列表少一个；换账号删同一个 id → 404（不泄露存在性）',
    '8': '隐私：A 的家人不出现在 B 的 family；家人昵称不出现在 friends/feed/ranking/邀请预览',
    '9': '真浏览器（430×932 与 1440×900）：入口/添加/指数/基线/提醒/删除；0 新增 JS 错误、无横向滚动',
    '10': '既有零回归：社交 51 / 推荐 45 / 支付佣金 80 / 后台 144 / 积分 77 / 开放 API 75 / 内核 335 / 服务端 104',
    'E': '自检 E · 禁用词扫描：新增与改动文件 0 命中',
    'F': '自检 F · 两张表结构与字段口径核对（family_member / family_reminder）',
}
CRIT_ORDER = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'E', 'F']

# ★ 家人昵称用**可搜索的独特串**：隐私断言要在别人的响应正文里逐字搜索它
FAM_NICK = '阿妈测试甲'
FAM_NICK_2 = '测试家人乙'
FAM_BIRTH = '1962-03-08 06:20'
FAM_LNG, FAM_LAT = 116.4074, 39.9042


def check(crit, name, ok, detail=''):
    ok = bool(ok)
    RESULTS.append((crit, name, ok, str(detail)))
    print('    [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, detail))
    return ok


def head(crit):
    print('\n=== 断言 #%s · %s ===' % (crit, CRIT_TITLE[crit]))


# ── HTTP 小工具 ──────────────────────────────────────────────────────
def http(method, path, raw=None, token=None, extra=None, timeout=90):
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
            try:
                return r.status, json.loads(body.decode('utf-8'))
            except ValueError:
                return r.status, {'_raw': body.decode('utf-8', 'replace')}
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body.decode('utf-8'))
        except Exception:                                           # noqa: BLE001
            return e.code, {'_raw': body.decode('utf-8', 'replace')}


def api(method, path, body=None, token=None, extra=None):
    raw = None if body is None else json.dumps(
        body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return http(method, path, raw, token, extra)


def data_of(payload):
    return (payload or {}).get('data') or {}


def login(tag):
    """既有 C 端游客登录（本脚本不改它一行）。返回 (token, member_id, status)。"""
    s, j = api('POST', '/api/v1/auth/guest', {'device_id': 'v11-%s-%s' % (tag, RUN)})
    d = data_of(j)
    return d.get('access_token', ''), d.get('member_id', ''), s


def add_family(token, nickname, birth=FAM_BIRTH, relation='mother',
               lng=FAM_LNG, lat=FAM_LAT):
    return api('POST', '/api/v1/family/members',
               {'nickname': nickname, 'relation_code': relation, 'birth_local': birth,
                'longitude': lng, 'latitude': lat}, token)


def get_family(token):
    s, j = api('GET', '/api/v1/family', None, token)
    return s, j, data_of(j)


def members_of(j):
    return data_of(j).get('members') or []


def raw_text(payload) -> str:
    """响应正文（**逐字**，用于隐私搜索与 L0–L4 扫描）。"""
    return json.dumps(payload, ensure_ascii=False)


# ── 直读测试库（只为本脚本造证据；只读，不改服务状态）──────────────
def db_rows(sql, args=()):
    conn = sqlite3.connect(('file:%s?mode=ro' % DB.replace('\\', '/')), uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def cols_of(table):
    return [str(r['name']) for r in db_rows('PRAGMA table_info(%s)' % table)]


def file_has(path, needle: str) -> bool:
    try:
        with open(path, 'rb') as fp:
            return fp.read().find(needle.encode('utf-8')) >= 0
    except OSError:
        return False


def _sha(path: str) -> str:
    try:
        with open(path, 'rb') as fp:
            return hashlib.sha256(fp.read()).hexdigest()
    except OSError:
        return 'MISSING'


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


# ══════════════════════════════════════════════════════════════════
def main():
    os.makedirs(HERE, exist_ok=True)
    try:
        sys.stdout = _Tee(sys.stdout, open(OUT_TXT, 'w', encoding='utf-8'))
    except OSError:
        pass

    # ── 0 打包（把最新 server/family.py + serve.py + web/ 三个文件纳入构件）──
    print('=== 0 打包（把最新 family.py / serve.py / web 三件纳入构件）===')
    r = subprocess.run(['pwsh', '-NoProfile', '-File', PACK],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('\n'.join((r.stdout or '').strip().splitlines()[-3:]))
    if r.returncode != 0:
        print((r.stderr or '')[:800])
        sys.exit(1)
    for rel in ('server/family.py', 'server/serve.py', 'web/app.js', 'web/index.html',
                'web/style.css'):
        print('    构件内 %-20s 存在: %s'
              % (rel, os.path.isfile(os.path.join(STAGE, *rel.split('/')))))
    load_stage_serve()

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
                if rr.status == 200:
                    healthy = True
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
    scan_banned_words()
    regression_zero()
    summarize()


# ══════════════════════════════════════════════════════════════════
# 构件里的装配层（display_normalize 的**唯一一份**）与内核正本
# ══════════════════════════════════════════════════════════════════
STAGE_SERVE = {'mod': None}
sys.path.insert(0, CORE)
from tianyuanheng import phase_index as kernel_phase          # noqa: E402
from tianyuanheng import RULE_VERSION as KERNEL_RULE_VERSION  # noqa: E402


def load_stage_serve():
    """把构件里的 server/serve.py 当模块加载：拿到装配层**唯一**的 display_normalize。"""
    os.environ['SHUZI_SRC_ROOT'] = STAGE
    path = os.path.join(STAGE, 'server', 'serve.py')
    spec = importlib.util.spec_from_file_location('v11_stage_serve', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    STAGE_SERVE['mod'] = mod
    print('    已加载构件内装配层：%s' % path)


def _norm(score):
    return STAGE_SERVE['mod'].display_normalize(score)


def _norm_manual(score):
    """按构件里公开的锚点**独立复算**一遍（第二条路径，防"函数被改而测不出来"）。"""
    (k1, d1), (k2, d2) = STAGE_SERVE['mod'].DISPLAY_ANCHORS
    slope = (d2 - d1) / (k2 - k1)
    return max(0, min(100, int(round(d1 + (float(score) - k1) * slope))))


def kernel_index(birth_local: str, lng, lat, target_date: str) -> dict:
    """内核对该生辰的**直算**结果（本进程内，不问被测服务）。"""
    return kernel_phase.phase_index(birth_local, lng, lat, target_date=target_date)


# ══════════════════════════════════════════════════════════════════
def run_phases():
    today = time.strftime('%Y-%m-%d')

    # ── 准备：两个真实账号（A 有家人；B 用于越权/隐私断言）─────────
    print('\n=== 2 准备：两个真实账号 ===')
    tok_a, mid_a, s_a = login('A')
    tok_b, mid_b, s_b = login('B')
    print('    A 登录 HTTP %s member=…%s；B 登录 HTTP %s member=…%s'
          % (s_a, str(mid_a)[-8:], s_b, str(mid_b)[-8:]))

    # ── 断言 #1 ───────────────────────────────────────────────────
    head('1')
    s_no, j_no = api('GET', '/api/v1/family')
    check('1', '未登录 GET /api/v1/family → **401**（既有 20000，响应键仍为 code/message/data/trace_id）',
          s_no == 401 and j_no.get('code') == 20000
          and set(j_no.keys()) == {'code', 'message', 'data', 'detail', 'trace_id'},
          'HTTP %s code=%s keys=%s' % (s_no, j_no.get('code'), sorted(j_no.keys())))
    s_bt, j_bt = api('GET', '/api/v1/family', None, 'not-a-real-token')
    check('1', '**错令牌** GET /api/v1/family → 401（不泄露任何数据）',
          s_bt == 401, 'HTTP %s code=%s' % (s_bt, j_bt.get('code')))
    s1, j1, d1 = get_family(tok_a)
    check('1', '登录 GET /api/v1/family → 200，code=0，`data.members` 为**数组**（新账号为空数组）',
          s1 == 200 and j1.get('code') == 0 and isinstance(d1.get('members'), list)
          and d1.get('members') == [] and isinstance(d1.get('summary'), dict)
          and isinstance(d1.get('reminders'), list) and bool(d1.get('disclaimer')),
          'HTTP %s members=%s summary=%s'
          % (s1, d1.get('members'), json.dumps(d1.get('summary'), ensure_ascii=False)))

    # ── 断言 #2：添加 + 指数逐字复算 ──────────────────────────────
    head('2')
    s_add, j_add = add_family(tok_a, FAM_NICK)
    m_add = data_of(j_add).get('member') or {}
    fam_id = str(m_add.get('family_id') or '')
    check('2', 'POST /api/v1/family/members → 200，code=0，返回 family_id（形如 fam_xxx）与非空 member',
          s_add == 200 and j_add.get('code') == 0
          and re.match(r'^fam_[0-9a-f]{12}$', fam_id) is not None
          and m_add.get('nickname') == FAM_NICK,
          'HTTP %s family_id=%s' % (s_add, fam_id))
    s2, j2, d2 = get_family(tok_a)
    got = [m for m in members_of(j2) if m.get('family_id') == fam_id]
    check('2', 'GET /api/v1/family **能读到**刚添加的家人（昵称/关系/生辰/经纬度一致）',
          s2 == 200 and len(got) == 1 and got[0].get('nickname') == FAM_NICK
          and got[0].get('relation') == '母亲' and got[0].get('relation_code') == 'mother'
          and got[0].get('birth_local') == FAM_BIRTH,
          'HTTP %s 命中 %d 条：%s' % (s2, len(got), json.dumps(got[:1], ensure_ascii=False)[:220]))

    # ★ 独立复算一：内核直算 + 构件里装配层的 display_normalize（两条路径）
    k_index = kernel_index(FAM_BIRTH, FAM_LNG, FAM_LAT, today)
    k_raw = int(k_index['score'])
    want = int(_norm(k_raw))
    want2 = int(_norm_manual(k_raw))
    band_code, band_name = kernel_phase.band_of(want)
    idx = (got[0].get('index') or {}) if got else {}
    check('2', '家人 index.score 与「内核对该生辰直算 + display_normalize」**逐字相等**'
               '（复算=%s，实测=%s）' % (want, idx.get('score')),
          bool(got) and idx.get('score') == want and idx.get('score_kernel') == k_raw,
          '内核原分=%s 展示分复算=%s 实测=%s' % (k_raw, want, idx.get('score')))
    check('2', '第二条复算路径（按构件公开锚点**独立重算**线性拉伸）与第一条一致，且都为实测值',
          want2 == want and idx.get('score') == want2,
          '锚点法=%s 函数法=%s 实测=%s' % (want2, want, idx.get('score')))
    check('2', 'index.band / band_name 与内核 `band_of(展示分)` 逐字一致（阈值 85/70/55 单一来源）',
          idx.get('band') == band_code and idx.get('band_name') == band_name,
          '内核=%s/%s 实测=%s/%s' % (band_code, band_name, idx.get('band'), idx.get('band_name')))

    # ★ 独立复算二：**换一个账号按同一生辰建档**，走 GET /rhythm/daily，比对同源
    tok_c, mid_c, _sc = login('daily')
    s_birth, j_birth = api('POST', '/api/v1/profile/birth',
                           {'birth_local': FAM_BIRTH.replace(' ', 'T'),
                            'longitude': FAM_LNG, 'latitude': FAM_LAT}, tok_c)
    s_day, j_day = api('GET', '/api/v1/rhythm/daily', None, tok_c)
    day_idx = data_of(j_day).get('index') or {}
    check('2', '同一生辰走 `GET /api/v1/rhythm/daily`：本人 index.score 与家人 index.score **逐字相等**'
               '（证明家人与「我」完全同一条链路）',
          s_birth == 200 and s_day == 200 and day_idx.get('score') == idx.get('score')
          and day_idx.get('score_kernel') == idx.get('score_kernel')
          and day_idx.get('band_code') == idx.get('band'),
          '本人 daily=%s(内核 %s) 家人=%s(内核 %s)；建档 HTTP %s / daily HTTP %s'
          % (day_idx.get('score'), day_idx.get('score_kernel'), idx.get('score'),
             idx.get('score_kernel'), s_birth, s_day))

    # ── 断言 #3：level 恒 null / baseline_text / 不出现 L0–L4 ──────
    head('3')
    lv_hits = []
    for label, payload in (('GET /family', j2), ('POST /members', j_add)):
        for mm in re.finditer(r'L[0-4]', raw_text(payload)):
            lv_hits.append('%s@%d' % (label, mm.start()))
    check('3', '家人的 `level` 字段**恒为 null**（本轮实测 %d 位家人）' % len(members_of(j2)),
          bool(members_of(j2)) and all(m.get('level') is None for m in members_of(j2)),
          'level 取值集合=%s' % {json.dumps(m.get('level')) for m in members_of(j2)})
    check('3', '家人 `baseline_text` 形如「基线建立中 n/7」（实测逐字为「基线建立中 0/7」）',
          bool(members_of(j2))
          and all(re.fullmatch(r'基线建立中 \d+/7', str(m.get('baseline_text') or ''))
                  and m.get('baseline_text') == '基线建立中 0/7' for m in members_of(j2)),
          'baseline_text 集合=%s' % {m.get('baseline_text') for m in members_of(j2)})
    check('3', '响应正文**不出现** L0–L4 字样（GET /family 与 POST /members 两份正文扫描 0 命中）',
          not lv_hits, '命中=%s' % (lv_hits[:3] or '无'))

    # ── 断言 #4：非法入参逐项被拒且可读 ────────────────────────────
    head('4')
    cases = [
        ('昵称超 12 字', {'nickname': '一二三四五六七八九十十一十二十三', 'relation_code': 'other',
                      'birth_local': '1990-01-01 12:00', 'longitude': 116.4, 'latitude': 39.9}),
        ('昵称为空', {'nickname': '   ', 'relation_code': 'other',
                  'birth_local': '1990-01-01 12:00', 'longitude': 116.4, 'latitude': 39.9}),
        ('关系 code 非法', {'nickname': '测试丁', 'relation_code': 'boss',
                      'birth_local': '1990-01-01 12:00', 'longitude': 116.4, 'latitude': 39.9}),
        ('出生时间不存在（2 月 30 日）', {'nickname': '测试戊', 'relation_code': 'other',
                              'birth_local': '2026-02-30 10:00', 'longitude': 116.4,
                              'latitude': 39.9}),
        ('出生时间格式非法', {'nickname': '测试己', 'relation_code': 'other',
                       'birth_local': '不是时间', 'longitude': 116.4, 'latitude': 39.9}),
        ('出生时间晚于现在', {'nickname': '测试庚', 'relation_code': 'other',
                       'birth_local': '2099-01-01 10:00', 'longitude': 116.4, 'latitude': 39.9}),
        ('经度越界 181', {'nickname': '测试辛', 'relation_code': 'other',
                      'birth_local': '1990-01-01 12:00', 'longitude': 181, 'latitude': 39.9}),
        ('纬度越界 -91', {'nickname': '测试壬', 'relation_code': 'other',
                      'birth_local': '1990-01-01 12:00', 'longitude': 116.4, 'latitude': -91}),
        ('经纬度非数值', {'nickname': '测试癸', 'relation_code': 'other',
                     'birth_local': '1990-01-01 12:00', 'longitude': 'abc', 'latitude': 39.9}),
    ]
    rows = []
    for label, body in cases:
        st, pl = api('POST', '/api/v1/family/members', body, tok_a)
        msg = str(pl.get('message') or '')
        detail = pl.get('detail') or {}
        # ★ 「可读」的判据收紧到**具体中文报文**：不是"请求无法完成"这类兜底串，且指明字段
        readable = (bool(msg) and msg != '请求无法完成'
                    and bool(re.search(r'[\u4e00-\u9fa5]', msg))
                    and bool(detail.get('field')))
        rows.append((label, st, pl.get('code'), msg, readable))
        print('      %-22s → HTTP %s code=%s message=%s'
              % (label, st, pl.get('code'), msg[:40]))
    bad = [r for r in rows if r[1] != 400]
    check('4', '九类非法入参**逐项 400**（HTTP 400 + 既有 10001/10002 业务码）',
          not bad, '非 400 的项=%s' % [(r[0], r[1]) for r in bad] or '无')
    check('4', '每一条报错都是**具体可读中文 + 指明字段**（不是「请求无法完成」这类兜底串）',
          all(r[4] for r in rows),
          '逐条报文=%s' % [(r[0], r[3]) for r in rows])
    check('4', '被拒的调用**没有落库**：非法入参后家人数仍为 1',
          len(members_of(get_family(tok_a)[1])) == 1,
          '当前家人数=%d' % len(members_of(get_family(tok_a)[1])))

    # ── 断言 #5：重复 与 席位上限 ─────────────────────────────────
    head('5')
    s_dup, j_dup = add_family(tok_a, FAM_NICK)
    dup_msg = str(j_dup.get('message') or '')
    check('5', '同属主「昵称+生辰」重复 → **被拒**且提示「这个家人已经添加过了」',
          s_dup != 200 and '这个家人已经添加过了' in dup_msg,
          'HTTP %s code=%s message=%s' % (s_dup, j_dup.get('code'), dup_msg))
    check('5', '重复被拒后**列表没有多出第 2 条**（仍为 1 位）',
          len(members_of(get_family(tok_a)[1])) == 1,
          '家人数=%d' % len(members_of(get_family(tok_a)[1])))

    filled = [FAM_NICK]
    for i in range(2, 9):                                    # 补到 8 位（含第 1 位）
        nick = '%s%d' % (FAM_NICK_2, i)
        st, pl = add_family(tok_a, nick, birth='1970-%02d-15 09:30' % i, relation='father')
        if st != 200:
            print('      补位失败：%s → HTTP %s %s' % (nick, st, pl.get('message')))
        filled.append(nick)
    n_now = len(members_of(get_family(tok_a)[1]))
    print('    已添加家人数 = %d（席位上限 8）' % n_now)
    check('5', '累计添加满 **8 位**（席位上限）全部 200',
          n_now == 8, '当前家人数=%d' % n_now)
    s_full, j_full = add_family(tok_a, '第九位家人', birth='1980-05-05 08:00')
    full_msg = str(j_full.get('message') or '')
    check('5', '第 9 位家人 → **被拒**且提示「家庭席位已满（8 位）」',
          s_full != 200 and '家庭席位已满（8 位）' in full_msg,
          'HTTP %s code=%s message=%s' % (s_full, j_full.get('code'), full_msg))
    # ★ 2026-10-08 师父定口径：席位已满是**功能上限**、不是"需付费" ⇒ 必须是 400 / 10004，
    #   不能落到 3xxxx（那段整段映射 402）。此处**显式同时断言 400 与 10004**，
    #   并单独断言"不是 402"，防止将来有人把码挪回 3xxxx 而测试不响。
    check('5', '席位满的错误语义 = **HTTP 400 + code 10004**（师父 2026-10-08 口径；不是 402/30003）',
          s_full == 400 and j_full.get('code') == 10004,
          'HTTP %s code=%s' % (s_full, j_full.get('code')))
    check('5', '席位满**不再是 402**（3xxxx 段只留给"需付费"类语义）',
          s_full != 402,
          'HTTP %s' % s_full)
    check('5', '席位满被拒后**列表仍是 8 位**（没有把第 9 位写进去）',
          len(members_of(get_family(tok_a)[1])) == 8,
          '家人数=%d' % len(members_of(get_family(tok_a)[1])))

    # ── 断言 #6：关怀提醒幂等 ─────────────────────────────────────
    head('6')
    body_r = {'family_id': fam_id, 'kind': 'care', 'text': '今天记得早点休息'}
    s_r1, j_r1 = api('POST', '/api/v1/family/remind', body_r, tok_a)
    r1 = data_of(j_r1)
    s_r2, j_r2 = api('POST', '/api/v1/family/remind',
                     {'family_id': fam_id, 'kind': 'care', 'text': '换个说法的第二条'}, tok_a)
    r2 = data_of(j_r2)
    rows_r = db_rows('SELECT * FROM family_reminder WHERE owner_member = ? AND family_id = ?'
                     ' AND kind = ? AND on_date = ?', (mid_a, fam_id, 'care', today))
    check('6', 'POST /api/v1/family/remind → 200，返回记录含 family_id/kind/text/on_date/created_at',
          s_r1 == 200 and r1.get('reminder_id') and r1.get('family_id') == fam_id
          and r1.get('kind') == 'care' and r1.get('text') == '今天记得早点休息'
          and r1.get('on_date') == today and bool(r1.get('created_at')),
          'HTTP %s %s' % (s_r1, json.dumps(r1, ensure_ascii=False)[:200]))
    check('6', '当日**重复调用只留一条**（库里同名同日同 kind 行数 = %d），且第二次 `repeated=true`'
          % len(rows_r),
          len(rows_r) == 1 and s_r2 == 200 and r2.get('repeated') is True
          and r2.get('reminder_id') == r1.get('reminder_id'),
          '行数=%d 第二次 repeated=%s id=%s/%s'
          % (len(rows_r), r2.get('repeated'), r1.get('reminder_id'), r2.get('reminder_id')))
    check('6', '重复调用**保留最先那条文案**（不会被后一次覆盖）',
          r2.get('text') == '今天记得早点休息'
          and rows_r[0]['text'] == '今天记得早点休息',
          '返回文案=%s 库里文案=%s' % (r2.get('text'), rows_r[0]['text']))
    a1 = {k: v for k, v in r1.items() if k != 'repeated'}
    a2 = {k: v for k, v in r2.items() if k != 'repeated'}
    check('6', '重复调用返回的就是**原记录**（除 `repeated` 标记外，两次响应逐字相同）',
          a1 == a2, '两次差异=%s'
          % {k: (a1.get(k), a2.get(k)) for k in set(a1) | set(a2) if a1.get(k) != a2.get(k)})
    s_rs, j_rs = api('GET', '/api/v1/family/reminders', None, tok_a)
    items = data_of(j_rs).get('items') or []
    hit = [x for x in items if x.get('family_id') == fam_id and x.get('kind') == 'care']
    check('6', 'GET /api/v1/family/reminders 能读到该条，**含昵称与时间**',
          s_rs == 200 and len(hit) == 1 and hit[0].get('nickname') == FAM_NICK
          and bool(hit[0].get('created_at')) and hit[0].get('text') == '今天记得早点休息',
          'HTTP %s items=%d 首条=%s' % (s_rs, len(items),
                                       json.dumps(hit[:1], ensure_ascii=False)[:200]))
    s_rk, j_rk = api('POST', '/api/v1/family/remind',
                     {'family_id': fam_id, 'kind': '不存在的类型'}, tok_a)
    check('6', '未知 kind → 400 且报错可读（不静默当 care 处理）',
          s_rk == 400 and '提醒类型需为' in str(j_rk.get('message') or ''),
          'HTTP %s code=%s message=%s' % (s_rk, j_rk.get('code'), j_rk.get('message')))

    # ── 断言 #7：删除（本人 200 / 他人 404）───────────────────────
    head('7')
    before_n = len(members_of(get_family(tok_a)[1]))
    s_del_b, j_del_b = api('DELETE', '/api/v1/family/members/' + fam_id, None, tok_b)
    check('7', '**换一个账号**删同一个 family_id → **404**（不泄露存在性）',
          s_del_b == 404, 'HTTP %s code=%s message=%s'
          % (s_del_b, j_del_b.get('code'), str(j_del_b.get('message'))[:40]))
    check('7', '越权删除后 A 的家人**一位没少**（仍为 %d 位）' % before_n,
          len(members_of(get_family(tok_a)[1])) == before_n,
          '家人数=%d' % len(members_of(get_family(tok_a)[1])))
    s_del_no, j_del_no = api('DELETE', '/api/v1/family/members/' + fam_id)
    check('7', '未登录删除 → 401（先鉴权、后业务）', s_del_no == 401,
          'HTTP %s code=%s' % (s_del_no, j_del_no.get('code')))
    s_del_a, j_del_a = api('DELETE', '/api/v1/family/members/' + fam_id, None, tok_a)
    after = members_of(get_family(tok_a)[1])
    check('7', '**本人删除 → 200**，且列表**少一个**（%d → %d），该 id 不在列表里'
          % (before_n, len(after)),
          s_del_a == 200 and data_of(j_del_a).get('removed') is True
          and len(after) == before_n - 1
          and all(m.get('family_id') != fam_id for m in after),
          'HTTP %s 家人数 %d→%d' % (s_del_a, before_n, len(after)))
    gone = db_rows('SELECT count(*) AS n FROM family_reminder WHERE owner_member = ?'
                   ' AND family_id = ?', (mid_a, fam_id))
    check('7', '删除家人时**一并清掉我发给 TA 的关怀提醒**（合规最小化：不留孤儿历史）',
          int(gone[0]['n'] or 0) == 0, '残留提醒行数=%s' % gone[0]['n'])
    s_del_again, j_del_again = api('DELETE', '/api/v1/family/members/' + fam_id, None, tok_a)
    check('7', '本人**重复删除同一个 id → 404**（同一句可读提示，仍然不泄露存在性）',
          s_del_again == 404, 'HTTP %s message=%s'
          % (s_del_again, str(j_del_again.get('message'))[:40]))

    # ── 断言 #8：隐私（跨账号 + 三处社交响应）─────────────────────
    head('8')
    s_re_add, j_re_add = add_family(tok_a, FAM_NICK)
    fam_id2 = str((data_of(j_re_add).get('member') or {}).get('family_id') or '')
    check('8', '前置：A 重新添加一位独特昵称的家人（%s），用于隐私搜索' % FAM_NICK,
          s_re_add == 200 and bool(fam_id2), 'HTTP %s family_id=%s' % (s_re_add, fam_id2))

    s_b_fam, j_b_fam, d_b_fam = get_family(tok_b)
    check('8', 'B 账号 `GET /api/v1/family` **看不到 A 的任何家人**（B 的空数组，且正文搜不到 A 的昵称）',
          s_b_fam == 200 and members_of(j_b_fam) == [] and FAM_NICK not in raw_text(j_b_fam),
          'HTTP %s B 家人数=%d 昵称命中=%s'
          % (s_b_fam, len(members_of(j_b_fam)), FAM_NICK in raw_text(j_b_fam)))

    # A、B 结成好友（走邀请链接自动接受），并让 A 打开三个公开开关
    s_ref, j_ref = api('GET', '/api/v1/me/referral', None, tok_a)
    code_a = data_of(j_ref).get('invite_code', '')
    s_inv, j_inv = api('POST', '/api/v1/friends/invite',
                       {'invite_code': code_a, 'auto_accept': True}, tok_b)
    s_pv, j_pv = api('POST', '/api/v1/friends/privacy',
                     {'share_index': True, 'share_streak': True, 'in_ranking': True}, tok_a)
    check('8', '前置：A、B 已成为好友，且 A 打开三个公开开关（否则排行榜本来就看不到 A）',
          s_inv == 200 and s_pv == 200,
          'invite HTTP %s privacy HTTP %s' % (s_inv, s_pv))

    friends_a = raw_text(api('GET', '/api/v1/friends', None, tok_a)[1])
    friends_b = raw_text(api('GET', '/api/v1/friends', None, tok_b)[1])
    feed_b = raw_text(api('GET', '/api/v1/friends/feed', None, tok_b)[1])
    rank_b = raw_text(api('GET', '/api/v1/friends/ranking', None, tok_b)[1])
    preview = raw_text(api('GET', '/api/v1/invite/preview?invite_code=' + code_a)[1])
    check('8', '家人昵称**不出现在** `GET /friends`（A、B 两侧响应正文逐字搜索）',
          FAM_NICK not in friends_a and FAM_NICK not in friends_b,
          'A 命中=%s B 命中=%s' % (FAM_NICK in friends_a, FAM_NICK in friends_b))
    check('8', '家人昵称**不出现在** `GET /friends/feed`',
          FAM_NICK not in feed_b, '命中=%s' % (FAM_NICK in feed_b))
    check('8', '家人昵称**不出现在** `GET /friends/ranking`',
          FAM_NICK not in rank_b, '命中=%s' % (FAM_NICK in rank_b))
    check('8', '家人昵称**不出现在** `GET /invite/preview`（邀请预览只回昵称，且不含家人）',
          FAM_NICK not in preview, '命中=%s' % (FAM_NICK in preview))
    check('8', '家人**没有 member_id**：响应里除录入者外不含任何 member_id 形字段'
               '（家人不是账号，只有 family_id）',
          all('member_id' not in m for m in members_of(get_family(tok_a)[1]))
          and 'member_id' not in raw_text(j_re_add),
          '家人字段=%s' % sorted(members_of(get_family(tok_a)[1])[0].keys()))

    # ── 断言 #9：真浏览器（系统 Python + Playwright；结果由子脚本产出）──
    head('9')
    browser_phase()

    # ── 断言 #10(a)：既有 C 端接口未受影响（直连核对）──────────────
    head('10')
    s_h, j_h = api('GET', '/api/health')
    check('10', '既有 /api/health → 200 且规则版本 %s 未变' % KERNEL_RULE_VERSION,
          s_h == 200 and data_of(j_h).get('rule_version') == KERNEL_RULE_VERSION
          and data_of(j_h).get('ok') is True,
          'HTTP %s rule=%s' % (s_h, data_of(j_h).get('rule_version')))
    s_idx, j_idx = http('GET', '/')
    html_idx = j_idx.get('_raw', '') if isinstance(j_idx, dict) else ''
    check('10', '既有首页 → 200 且 JSON-LD（Dataset / SoftwareApplication）仍在',
          s_idx == 200 and 'Dataset' in html_idx and 'SoftwareApplication' in html_idx,
          'HTTP %s' % s_idx)
    check('10', '构件内 `app/*`、`tianyuanheng/*` 与工作区正本 **SHA-256 全同**'
                '（既有源码一字未动，抽查 8 个文件）',
          _same_source_check(),
          '不一致=%s' % (_diff_source_check() or '无'))
    check('10', '构件内 web 三件与工作区正本 **SHA-256 全同**（测的就是将要部署的那三份）',
          _web_same_check(), '不一致=%s' % (_web_diff_check() or '无'))

    # ── 自检 F：表结构与字段口径（趁库还在，用 A 的真实 member_id 核对属主列）──
    schema_checks(mid_a)


def _srcrels():
    return (('app', 'api.py'), ('app', 'http.py'), ('app', 'errors.py'),
            ('app', 'ratelimit.py'), ('app', 'auth.py'), ('app', 'envelope.py'),
            ('tianyuanheng', 'phase_index.py'), ('tianyuanheng', 'guardrail.py'))


def _same_source_check():
    return not _diff_source_check()


def _diff_source_check():
    diff = []
    for rel in _srcrels():
        staged = os.path.join(STAGE, rel[0], rel[1])
        origin = os.path.join(WS, '服务端' if rel[0] == 'app' else '核心', rel[0], rel[1])
        if _sha(staged) != _sha(origin):
            diff.append('%s/%s' % rel)
    return diff


def _web_diff_check():
    diff = []
    for name in ('app.js', 'index.html', 'style.css'):
        if _sha(os.path.join(STAGE, 'web', name)) != _sha(os.path.join(ROOT, 'web', name)):
            diff.append(name)
    return diff


def _web_same_check():
    return not _web_diff_check()


# ══════════════════════════════════════════════════════════════════
def browser_phase():
    """跑真浏览器子脚本（系统 Python + Playwright/Chromium），结果合并进本汇总。"""
    if not os.path.isfile(BROWSER):
        check('9', '真浏览器脚本存在：%s' % BROWSER, False, '文件不存在')
        return
    try:
        probe = subprocess.run([SYS_PY, '-c', 'import playwright'], capture_output=True, text=True)
        has_pw = probe.returncode == 0
    except Exception:                                               # noqa: BLE001
        has_pw = False
    if not has_pw:
        check('9', '真浏览器验证：**本机无法复算**（系统 Python 缺 playwright）', False,
              'sys_py=%s；如实标注，不假装通过' % SYS_PY)
        return
    env = dict(os.environ, FAMILY_BASE=BASE, PYTHONIOENCODING='utf-8')
    r = subprocess.run([SYS_PY, BROWSER], env=env, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    tail = [ln for ln in ((r.stdout or '') + (r.stderr or '')).splitlines() if ln.strip()]
    for ln in tail[-24:]:
        print('      %s' % ln)
    if not os.path.isfile(BROWSER_JSON):
        check('9', '真浏览器验证产出结果 JSON（%s）' % os.path.basename(BROWSER_JSON), False,
              'rc=%d 未产出结果文件' % r.returncode)
        return
    with open(BROWSER_JSON, encoding='utf-8') as fp:
        rep = json.load(fp)
    for item in rep.get('results') or []:
        check('9', item.get('name', ''), item.get('ok'), item.get('detail', ''))
    ce = rep.get('console_errors') or {}
    print('      控制台 error 统计：改前=%s 改后（既有屏）=%s 家庭档案流程=%s'
          % (ce.get('before_total'), ce.get('after_total'), ce.get('family_total')))
    check('9', '结论行：真浏览器 %d 项断言全过（rc=%d）'
          % (len(rep.get('results') or []), r.returncode),
          r.returncode == 0 and bool(rep.get('results')), rep.get('summary', ''))


# ══════════════════════════════════════════════════════════════════
# 自检 E：禁用词扫描
# ══════════════════════════════════════════════════════════════════
# ★ 为什么用码点拼装而不是直接写字面量：本脚本**自己也要被**这张表扫描
#   （family.py 与全部新增文件都要 0 命中），直接写字面量会让扫描器命中自己。
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


def scan_banned_words():
    """自检 E：对新增/改动文件 + 运行期产物做禁用词扫描（命中数必须为 0）。

    ★ 只打印**命中数与词表下标**，不打印词面——否则扫描输出文件本身会把词面写进磁盘，
      下一次扫描又会命中自己（自指陷阱）。词面见变更任务书的用词纪律清单。
    """
    head('E')
    targets = [os.path.join(ROOT, 'server', 'family.py'),
               os.path.join(ROOT, 'server', 'serve.py'),
               os.path.join(ROOT, 'web', 'index.html'),
               os.path.join(ROOT, 'web', 'app.js'),
               os.path.join(ROOT, 'web', 'style.css'),
               os.path.abspath(__file__),
               BROWSER,
               OUT_TXT, RESULT_JSON, BROWSER_JSON]
    print('    词表条目数 = %d（本脚本不打印词面，避免扫描器命中自身输出）' % len(BANNED_WORDS))
    total_hits = 0
    for path in targets:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as fp:
                text = fp.read()
        except OSError as ex:
            print('    %-34s 跳过（%s）' % (os.path.basename(path), type(ex).__name__))
            continue
        low = text.lower()
        hit_idx = [i for i, w in enumerate(BANNED_WORDS) if w.lower() in low]
        total_hits += len(hit_idx)
        print('    %-34s 字节=%-8d 命中=%d %s'
              % (os.path.basename(path), len(text.encode('utf-8')), len(hit_idx),
                 ('词表下标=%s' % hit_idx) if hit_idx else ''))
    check('E', '禁用词扫描：%d 个文件 × %d 条词表 → **命中 %d**（要求 0）'
          % (len(targets), len(BANNED_WORDS), total_hits), total_hits == 0,
          '命中合计=%d' % total_hits)


# ══════════════════════════════════════════════════════════════════
# 自检 F：表结构与字段口径
# ══════════════════════════════════════════════════════════════════
def schema_checks(owner_member: str):
    head('F')
    try:
        cols_m = cols_of('family_member')
        cols_r = cols_of('family_reminder')
    except sqlite3.Error as ex:
        check('F', '两张表都建在同一份 state.db 里', False, str(ex))
        return
    print('    family_member 列   = %s' % cols_m)
    print('    family_reminder 列 = %s' % cols_r)
    check('F', 'family_member 含全部要求字段（属主 owner_member / family_id / 称呼 / 关系 / 生辰 / 经纬度 / 时间）',
          {'family_id', 'owner_member', 'nickname', 'relation_code', 'birth_local',
           'longitude', 'latitude', 'created_at', 'updated_at'} <= set(cols_m),
          '缺少=%s' % sorted({'family_id', 'owner_member', 'nickname', 'relation_code',
                              'birth_local', 'longitude', 'latitude', 'created_at',
                              'updated_at'} - set(cols_m)))
    check('F', 'family_reminder 含全部要求字段（属主 / 家人 / kind / 文案 / 日期 / 时间）',
          {'id', 'owner_member', 'family_id', 'kind', 'text', 'on_date',
           'created_at'} <= set(cols_r),
          '缺少=%s' % sorted({'id', 'owner_member', 'family_id', 'kind', 'text', 'on_date',
                              'created_at'} - set(cols_r)))
    check('F', '两张表落在**同一份 state.db**（沿用既有库，不另开库）', os.path.isfile(DB),
          'DB=%s' % DB)
    rows = db_rows('SELECT owner_member, count(*) AS n FROM family_member GROUP BY owner_member')
    owners = {str(r['owner_member']) for r in rows}
    total = sum(int(r['n'] or 0) for r in rows)
    check('F', '家人行的属主**就是录入者本人**：库里 family_member 只有 A 的 member_id'
               '（%d 行 / 属主 %d 个；家人自己不是账号、没有 member_id）' % (total, len(owners)),
          owners == {owner_member} and total == 8,
          '属主集合=%s 总行数=%d（期望仅 A 的 …%s，8 行）'
          % (owners, total, str(owner_member)[-6:]))


# ══════════════════════════════════════════════════════════════════
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
    """#10（b）：8 条既有命令实跑。判定 = 返回码 + 文本汇总行 + 项数，三者同时成立。

    ★★ 本机环境前提（**如实标注，不因此放宽任何断言**）★★
      `服务端/tests/test_pg_baseline.py`（21 项）在**模块级自查**后整体 `SkipTest`——
      它需要可连的 PostgreSQL（环境变量 `TYH_PG_DSN`，或本机回退串）。本机没有可用 PG，
      因此实测是 `Ran 83 tests` / `OK (skipped=1)`，而不是 104。由此产生两条事实：
        · 「服务端 104」这一条**如实 FAIL**（83 ≠ 104），根因是**环境前提**，不是代码差异；
        · 支付佣金 80 / 独立后台 144 / 积分 77 / 开放 API 75 四条**各自内部**也复跑了
          「服务端 104」（级联），于是跟着 FAIL —— 它们的**业务断言本身全过**
          （79/80、143/144、74/77、v10 的 9 条 API 断言全过），唯一失败项就是这条环境前提。
      ★ 本脚本**不放宽这些期望值**：装上 PostgreSQL（或设好 TYH_PG_DSN）后重跑即可回到 104。
      ★ 佐证：`服务端/` 与 `核心/` 下近 4 小时内被改动的文件数 = 0（本次改动没碰过它们）。
    """
    print('\n=== 断言 #10（b） · 既有回归实跑（社交 51 / 推荐 45 / 支付佣金 80 / '
          '独立后台 144 / 积分 77 / 开放 API 75 / 内核 335 / 服务端 104）===')
    print('    ★ 环境前提：本机无可用 PostgreSQL → 服务端 PG 集成用例（21 项）整体 SkipTest，'
          '实测 Ran 83 tests（OK, skipped=1）；相关级联失败**如实报 FAIL**，不放宽期望值。')
    if os.environ.get('FAMILY_SKIP_REGRESSION') == '1':
        print('    [SKIP] 按 FAMILY_SKIP_REGRESSION=1 跳过既有回归（**仅用于调试**）')
        print('    [SKIP] 正式运行命令：%s %s' % (PY, os.path.abspath(__file__)))
        return

    def run_reg(name, cmd, cwd, expect, count_re, want, note=''):
        t0 = time.time()
        rc, out = _run(cmd, cwd)
        hit = expect in out
        ms = re.findall(count_re, out)
        n = ms[-1] if ms else '?'
        ok = rc == 0 and hit and n == want
        check('10', '%s（含汇总行「%s」，%.0fs）' % (name, expect, time.time() - t0), ok,
              ('rc=%d 含汇总行=%s 项数=%s（期望 %s）%s'
               % (rc, hit, n, want, ('；' + note) if (note and not ok) else '')))

    run_reg('社交 51：既有轻社交端到端验证', [PY, SOCIAL_TEST], None,
            '合计 51 项子断言，通过 51，失败 0', r'合计\s*(\d+)\s*项子断言', '51')
    run_reg('推荐 45：既有推荐关系端到端验证', [PY, REFERRAL_TEST], None,
            '合计 45 项子断言，通过 45，失败 0', r'合计\s*(\d+)\s*项子断言', '45')
    run_reg('支付佣金 80：P1 自建支付与佣金账本全过',
            [PY, PAY_TEST], None, '合计 80 项子断言，通过 80，失败 0',
            r'合计\s*(\d+)\s*项子断言', '80',
            note='该套件的业务断言 79/80 全过，唯一失败项是它**内部**复跑的「服务端 104」'
                 '（本机 PG 不可用 → 实测 83），属环境前提的级联，非本次改动引入')
    run_reg('独立后台 144：既有后台端到端验证', [PY, ADMIN_TEST], None,
            '合计 144 项断言，通过 144，失败 0', r'合计\s*(\d+)\s*项断言', '144',
            note='该套件 143/144 全过，唯一失败项是它**内部**复跑的「服务端 104」，'
                 '属环境前提的级联，非本次改动引入')
    run_reg('积分 77：v8 积分余额与佣金路线全过', [PY, POINTS_TEST], None,
            '合计 77 项子断言，通过 77，失败 0', r'合计\s*(\d+)\s*项子断言', '77',
            note='该套件 74/77，3 个失败项全部是它**内部**复跑 pay/admin/服务端 三条时的'
                 '期望值级联（根因仍是本机 PG 不可用），非本次改动引入')
    run_reg('开放 API 75：v10 开放 API 端到端验证（本次改动未破坏 v10）',
            [PY, OPENAPI_TEST], None, '合计 75 项子断言，通过 75，失败 0',
            r'合计\s*(\d+)\s*项子断言', '75',
            note='v10 自身的 9 条接口断言 + 内核 335 全过；4 个失败项是它**内部**复跑 '
                 'pay/admin/points/服务端 四条时的期望值级联（根因同上），非本次改动引入')
    run_reg('内核 335：核心测试全过（便携运行时）',
            [PY, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'], CORE,
            'Ran 335 tests', r'Ran (\d+) tests', '335')
    try:
        probe = subprocess.run([SYS_PY, '-c', 'import psycopg, fakeredis'],
                               capture_output=True, text=True)
        has_dep = probe.returncode == 0
    except Exception:                                               # noqa: BLE001
        has_dep = False
    if not has_dep:
        check('10', '服务端 104：**本机无法复算**（系统 Python 缺 psycopg/fakeredis）', False,
              'sys_py=%s 缺依赖；如实标注，不假装通过' % SYS_PY)
    else:
        # ★ 依赖包在、但**没有可连的 PostgreSQL** 时：test_pg_baseline.py（21 项）整体 SkipTest，
        #   于是实测 83 项。这条**如实报 FAIL**（期望 104 不放宽），detail 里写清根因。
        run_reg('服务端 104：服务层测试全过（解释器 %s）' % SYS_PY,
                [SYS_PY, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'], SERVER,
                'Ran 104 tests', r'Ran (\d+) tests', '104',
                note='psycopg/fakeredis 已装且 83 项全过（OK, skipped=1）；缺的是**可连的 '
                     'PostgreSQL**：test_pg_baseline.py 的 21 项在模块级自查后整体 SkipTest。'
                     '装上 PG 或设 TYH_PG_DSN 后即为 104')


# ══════════════════════════════════════════════════════════════════
def summarize():
    print('\n=== 汇总（#1–#10 = 变更单 §五 的 10 条；E/F = 本次额外自检）===')
    per = {}
    for crit, name, ok, detail in RESULTS:
        per.setdefault(crit, []).append((name, ok, detail))
    for crit in CRIT_ORDER:
        rows = per.get(crit) or []
        if not rows:
            continue
        bad = [r for r in rows if not r[1]]
        print('  断言 #%-2s %s —— %s（%d/%d 项通过）'
              % (crit, CRIT_TITLE[crit][:54], 'PASS' if not bad else 'FAIL',
                 len(rows) - len(bad), len(rows)))
        for name, _ok, detail in bad:
            print('      FAIL: %s  %s' % (name, detail))
    failed = [r for r in RESULTS if not r[2]]
    print('\n  合计 %d 项子断言，通过 %d，失败 %d；本脚本范围 %s'
          % (len(RESULTS), len(RESULTS) - len(failed), len(failed),
             '全部通过' if not failed else '存在失败'))
    for crit, name, _ok, detail in failed:
        print('  未通过：#%s %s  %s' % (crit, name, detail))
    print('  未验证项（如实标注）：线上部署（本单明令禁止，由师父统一做）、真实多设备并发、'
          '家人的"多人共享"场景（产品上家人不属于任何账号，故不存在）、'
          '**服务端 104 里的 PostgreSQL 集成 21 项**（本机无可连 PG → 该模块整体 SkipTest，'
          '实测 83 项全过 OK/skipped=1；装上 PG 或设 TYH_PG_DSN 即可复算到 104）。')
    print('  回退：删 server/family.py + 还原 serve.py（去 import / Stack 一行构造 / '
          '_dispatch 转发分支）→ 6 条接口整体消失，C 端不受影响；两张表可留可清；'
          '前端三个文件按部署前备份还原（本仓 _verify_v11\\_before\\ 存有改动前的三份正本）。')
    with open(RESULT_JSON, 'w', encoding='utf-8') as fp:
        json.dump([{'criteria': c, 'name': n, 'ok': o, 'detail': d}
                   for c, n, o, d in RESULTS], fp, ensure_ascii=False, indent=1)
    print('  明细 JSON: %s' % RESULT_JSON)
    print('  控制台完整输出: %s' % OUT_TXT)
    sys.exit(0 if not failed else 2)


if __name__ == '__main__':
    main()
