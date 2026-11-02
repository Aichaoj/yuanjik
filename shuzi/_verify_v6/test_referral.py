# -*- coding: utf-8 -*-
"""
端到端真服务验证 · 邀请链接 + 自动推荐绑定（v6）
================================================
对 **打包后的站点树**（`D:\\shuzi\\_dist\\_stage_site`）用**便携运行时**起真服务（端口 15092），
按变更单 `2026-10-08-邀请链接与自动推荐绑定` §五 的**第 1–5 条与第 8 条**逐条实测，
并补测师父追加的三项（昵称分享文案 / 免鉴权邀请预览 / 预览限流防枚举）。

脚本范围（如实说明，不假装做到）：
  · 验收 **#1–#5、#8** 在本脚本内逐条打印 PASS/FAIL；
  · 追加项 **A / B / C**（昵称与分享文案、邀请预览只回昵称、预览限流 61 次）一并逐条打印；
  · 验收 **#6 / #7** 是前端与浏览器实测（另一位同事负责），**不在本脚本范围**；
  · 验收 **#9**（绑定失败不阻塞注册）在既有 51 项社交验证与前端联调里覆盖，本脚本不重复；
  · 验收 **#10**（既有零回归）由三条既有命令单独跑：社交 51 项、内核 335、服务端 104。

运行：
    pwsh -NoProfile -File D:\\shuzi\\build_pack.ps1     # 生成 _stage_site（脚本内也会自动跑一次）
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v6\\test_referral.py

限流断言的口径（可复算，写在这里以免被当成"偶发"）：
    `GET /api/v1/invite/preview` 走既有 `app/ratelimit.py` 的 `LIMITS['api_anon'] = 60 次 / 60 秒`，
    令牌桶按 IP 计。本地真 HTTP 单次往返约 3–10ms，60 次连打在 1 秒内完成，
    桶内补回不足 1 个令牌，因此**第 61 次必被拒**（既有 `40000 RATE_LIMITED` / HTTP 429）。
    这一项放在**最后**跑（同 IP 桶已被打空，会让后续 preview 调用也被拒）。
"""
import json
import os
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
PY = r'D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe'
PACK = r'D:\Deepseek智能体\AI元健康\shuzi\build_pack.ps1'
HERE = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v6'
PORT = 15092
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, 'referral_v6.db')
LOG = os.path.join(HERE, 'test_referral.log')
RESULT_JSON = os.path.join(HERE, 'test_referral_result.json')
INVITE_URL_PREFIX = 'https://shuzi.yuanjk.cn/?invite='
RUN = time.strftime('%m%d%H%M%S')          # 本次运行的设备号后缀，保证每次都是"新用户"

RESULTS = []          # [(criteria, name, ok, detail)]
CRIT_TITLE = {
    '1': 'GET /me/referral 的 invite_url 逐字为 https://shuzi.yuanjk.cn/?invite=<code>',
    '2': 'B 用 A 的码 + auto_accept=true → 双方互为 accepted（无需 A 再确认）',
    '3': '同一调用后 referral 表新增且仅新增 1 行：referee=B、referrer=A',
    '4': 'B 再调用 / 改用 C 的码 → referral 仍指向 A（不可改绑）',
    '5': 'A 用自己的码 → 拒绝（30005），且不产生 referral 行',
    '8': '链接参数重复访问/刷新：不重复绑定、不报错（幂等）',
    'A': '补充 A · 改昵称后 nickname / share_text 立刻反映新昵称',
    'B': '补充 B · 免鉴权 GET /invite/preview：有效码回昵称、无效码 valid:false 且 200、只回昵称',
    'C': '补充 C · 预览限流：同 IP 连打 61 次，第 61 次被拒（40000 / HTTP 429）',
    'V': '补充 V · 不传 auto_accept 时仍是 pending（v3 原路径零改动）',
}
CRIT_ORDER = ['1', '2', '3', '4', '5', '8', 'A', 'B', 'C', 'V']


def check(crit, name, ok, detail=''):
    ok = bool(ok)
    RESULTS.append((crit, name, ok, str(detail)))
    print('    [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, detail))
    return ok


def head(crit):
    print('\n=== 断言 #%s · %s ===' % (crit, CRIT_TITLE[crit]))


# ── HTTP 小工具（与 _verify_v3/test_social.py 同一风格）──────────────
def api(method, path, body=None, token=None, timeout=60):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:                                   # 不传 token = 真的免鉴权调用
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:                                           # noqa: BLE001
            return e.code, {}


def data_of(payload):
    if isinstance(payload, tuple):
        payload = payload[1]
    return (payload or {}).get('data') or {}


def login(tag):
    """游客登录（真 HTTP）。返回 (token, member_id, http_status)。"""
    s, j = api('POST', '/api/v1/auth/guest', {'device_id': 'v6-%s-%s' % (tag, RUN)})
    d = data_of(j)
    return d.get('access_token', ''), d.get('member_id', ''), s


def short(mid):
    return (mid or '')[-8:]


def friend_row(token, friend_id):
    for f in data_of(api('GET', '/api/v1/friends', None, token)).get('friends') or []:
        if f.get('friend_id') == friend_id:
            return f
    return None


def invite_url_of(token):
    return data_of(api('GET', '/api/v1/me/referral', None, token)).get('invite_url')


# ── 邀请预览的调用计数器（限流断言要"可复算"，所以全脚本共用一本账）──
#   口径：`LIMITS['api_anon']` = 60 次 / 60 秒，按 IP 令牌桶计；
#   本脚本全程同一个 IP(127.0.0.1)，因此**全脚本成功次数应为 60**，
#   第 61 次调用（无论有效码还是无效码）必被拒。
PREVIEW_LOG = []          # [(第几次调用, HTTP, code)]


def preview(invite_code=None, token=None):
    """调一次 `GET /api/v1/invite/preview`；invite_code=None 表示**不带**该参数。"""
    path = '/api/v1/invite/preview'
    if invite_code is not None:
        path += '?invite_code=' + invite_code
    s, j = api('GET', path, None, token)
    PREVIEW_LOG.append((len(PREVIEW_LOG) + 1, s, j.get('code')))
    return s, j


def preview_ok_count():
    return len([1 for _n, s, _c in PREVIEW_LOG if s == 200])


# ── 直接读库（只读，服务在跑也能读）────────────────────────────────
def db_rows(sql, args=()):
    conn = sqlite3.connect('file:%s?mode=ro' % DB.replace('\\', '/'), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def referral_rows():
    return db_rows('SELECT referee_member_id, referrer_member_id, invite_code, bound_at,'
                   ' source FROM referral ORDER BY bound_at')


def referral_count(referee=None):
    if referee is None:
        return len(db_rows('SELECT 1 FROM referral'))
    return len(db_rows('SELECT 1 FROM referral WHERE referee_member_id = ?', (referee,)))


def pair_count(x, y):
    a, b = (x, y) if x <= y else (y, x)
    return len(db_rows('SELECT 1 FROM social_friend WHERE a_member = ? AND b_member = ?', (a, b)))


def print_referral_table():
    rows = referral_rows()
    print('\n=== referral 表（state.db 直读）===')
    print('    行数 = %d' % len(rows))
    for r in rows:
        print('    referee=%s referrer=%s invite_code=%s source=%s bound_at=%s'
              % (short(r['referee_member_id']), short(r['referrer_member_id']),
                 r['invite_code'], r['source'], r['bound_at']))
    return rows


def main():
    # ── 0 打包（把最新 server/social.py 纳入构件）────────────────────
    print('=== 0 打包 ===')
    r = subprocess.run(['pwsh', '-NoProfile', '-File', PACK],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('\n'.join((r.stdout or '').strip().splitlines()[-3:]))
    if r.returncode != 0:
        print((r.stderr or '')[:600])
        sys.exit(1)

    # ── 1 清库 + 起服务 ────────────────────────────────────────────
    print('\n=== 1 清库并起真服务（port %d）===' % PORT)
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(DB + suffix)
        except OSError:
            pass
    os.makedirs(os.path.join(STAGE, 'data'), exist_ok=True)
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST='127.0.0.1',
               SHUZI_PORT=str(PORT), SHUZI_DATA=DB, PYTHONIOENCODING='utf-8')
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
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:                                           # noqa: BLE001
            proc.kill()
        time.sleep(1)
        logf.close()
    summarize()


# ══════════════════════════════════════════════════════════════════
def run_phases():
    tok_a, id_a, sa = login('a')
    tok_b, id_b, sb = login('b')
    tok_c, id_c, sc = login('c')
    print('    A: HTTP %s member=…%s' % (sa, short(id_a)))
    print('    B: HTTP %s member=…%s' % (sb, short(id_b)))
    print('    C: HTTP %s member=…%s' % (sc, short(id_c)))

    # ── 断言 1：邀请链接逐字包含域名与码 ──────────────────────────
    head('1')
    ref_a = data_of(api('GET', '/api/v1/me/referral', None, tok_a))
    code_a = ref_a.get('invite_code')
    url_a = ref_a.get('invite_url')
    print('    A 的 invite_code=%s' % code_a)
    print('    A 的 invite_url =%s' % url_a)
    print('    A 的 share_text =%s' % ref_a.get('share_text'))
    check('1', 'invite_url 逐字等于 https://shuzi.yuanjk.cn/?invite=<invite_code>',
          url_a == INVITE_URL_PREFIX + (code_a or ''),
          'invite_url=%s' % url_a)
    check('1', 'URL 里带 ?invite= 且码为 8 位大写字母数字',
          '?invite=' in (url_a or '') and isinstance(code_a, str) and len(code_a) == 8
          and all(c.isdigit() or ('A' <= c <= 'Z') for c in code_a),
          'code=%s' % code_a)
    check('1', 'A 尚未被推荐（referred_by 为 null）',
          ref_a.get('referred_by') is None, 'referred_by=%s' % ref_a.get('referred_by'))
    check('1', 'GET /me/referral 是只读接口：连调两次不产生 referral 行',
          referral_count() == 0 and invite_url_of(tok_a) == url_a,
          'referral 行数=%d' % referral_count())

    # ── 断言 2：auto_accept 直接建立 accepted 好友关系 ────────────
    head('2')
    s2, j2 = api('POST', '/api/v1/friends/invite',
                 {'invite_code': code_a, 'auto_accept': True}, tok_b)
    print('    B 调 POST /friends/invite {auto_accept:true} → HTTP %s code=%s data=%s'
          % (s2, j2.get('code'), json.dumps(data_of(j2), ensure_ascii=False)))
    check('2', '调用成功且 status=accepted（跳过 pending/accept 流程）',
          s2 == 200 and j2.get('code') == 0 and data_of(j2).get('status') == 'accepted',
          'HTTP %s status=%s' % (s2, data_of(j2).get('status')))
    ra, rb = friend_row(tok_a, id_b), friend_row(tok_b, id_a)
    check('2', 'A 的 GET /friends 里 B 为 accepted', bool(ra) and ra.get('status') == 'accepted',
          'A→B=%s' % (ra or {}).get('status'))
    check('2', 'B 的 GET /friends 里 A 为 accepted', bool(rb) and rb.get('status') == 'accepted',
          'B→A=%s' % (rb or {}).get('status'))
    check('2', 'A 侧没有收到任何 pending 申请（无需 A 再确认）',
          all(f.get('status') == 'accepted' for f in
              (data_of(api('GET', '/api/v1/friends', None, tok_a)).get('friends') or [])),
          'A 的全部关系=%s' % [(f.get('status')) for f in
                              (data_of(api('GET', '/api/v1/friends', None, tok_a)).get('friends') or [])])
    check('2', '数据库里这一对关系只有 1 行', pair_count(id_a, id_b) == 1,
          'social_friend 行数=%d' % pair_count(id_a, id_b))

    # ── 断言 3：referral 表新增且仅新增 1 行 ─────────────────────
    head('3')
    rows = referral_rows()
    print('    referral 行数=%d %s' % (len(rows), json.dumps(rows, ensure_ascii=False)))
    b_rows = [r for r in rows if r['referee_member_id'] == id_b]
    check('3', 'referral 表总共只有 1 行', len(rows) == 1, '行数=%d' % len(rows))
    check('3', '这一行 referee=B 且 referrer=A',
          len(b_rows) == 1 and b_rows[0]['referrer_member_id'] == id_a,
          'referee=%s referrer=%s' % (short(b_rows[0]['referee_member_id']) if b_rows else '-',
                                      short(b_rows[0]['referrer_member_id']) if b_rows else '-'))
    check('3', 'invite_code=A 的码、source=link、bound_at 非空',
          bool(b_rows) and b_rows[0]['invite_code'] == code_a
          and b_rows[0]['source'] == 'link' and bool(b_rows[0]['bound_at']),
          'code=%s source=%s bound_at=%s'
          % (b_rows[0]['invite_code'] if b_rows else '-',
             b_rows[0]['source'] if b_rows else '-',
             b_rows[0]['bound_at'] if b_rows else '-'))
    check('3', 'referral 行只存 member_id / 邀请码（无手机号/真名/生辰列）',
          set(rows[0].keys()) == {'referee_member_id', 'referrer_member_id',
                                  'invite_code', 'bound_at', 'source'},
          '列=%s' % sorted(rows[0].keys()))

    # ── 断言 4：不可改绑 ──────────────────────────────────────────
    head('4')
    s4a, j4a = api('POST', '/api/v1/friends/invite',
                   {'invite_code': code_a, 'auto_accept': True}, tok_b)
    print('    B 重复用 A 的码 → HTTP %s code=%s referred_by=%s'
          % (s4a, j4a.get('code'), json.dumps(data_of(j4a).get('referred_by'), ensure_ascii=False)))
    check('4', 'B 再次调用不报错，返回体 referred_by 仍是 A',
          s4a == 200 and j4a.get('code') == 0
          and (data_of(j4a).get('referred_by') or {}).get('member_id') == id_a,
          'HTTP %s referred_by=%s' % (s4a, json.dumps(data_of(j4a).get('referred_by'),
                                                      ensure_ascii=False)))
    code_c = data_of(api('GET', '/api/v1/me/referral', None, tok_c)).get('invite_code')
    s4b, j4b = api('POST', '/api/v1/friends/invite',
                   {'invite_code': code_c, 'auto_accept': True}, tok_b)
    print('    B 改用 C 的码(%s) → HTTP %s code=%s referred_by=%s'
          % (code_c, s4b, j4b.get('code'),
             json.dumps(data_of(j4b).get('referred_by'), ensure_ascii=False)))
    check('4', 'B 改用 C 的码也不报错，referred_by 仍是 A（不可改绑）',
          s4b == 200 and j4b.get('code') == 0
          and (data_of(j4b).get('referred_by') or {}).get('member_id') == id_a,
          'HTTP %s referred_by=%s' % (s4b, json.dumps(data_of(j4b).get('referred_by'),
                                                      ensure_ascii=False)))
    check('4', 'GET /me/referral 的 referred_by 也是 A（与写路径同口径）',
          (data_of(api('GET', '/api/v1/me/referral', None, tok_b)).get('referred_by') or {}
           ).get('member_id') == id_a,
          'GET referred_by=%s' % json.dumps(
              data_of(api('GET', '/api/v1/me/referral', None, tok_b)).get('referred_by'),
              ensure_ascii=False))
    check('4', '库里 referee=B 只有 1 行，且 referrer 仍是 A',
          referral_count(id_b) == 1 and referral_rows()[0]['referrer_member_id'] == id_a,
          'referee=B 行数=%d referrer=%s' % (referral_count(id_b),
                                             short(referral_rows()[0]['referrer_member_id'])))

    # ── 断言 5：不可自荐 ──────────────────────────────────────────
    head('5')
    before = referral_count()
    s5, j5 = api('POST', '/api/v1/friends/invite',
                 {'invite_code': code_a, 'auto_accept': True}, tok_a)
    print('    A 用自己的码 → HTTP %s code=%s detail=%s'
          % (s5, j5.get('code'), json.dumps(j5.get('detail') or {}, ensure_ascii=False)))
    check('5', '被拒且错误码沿用既有 30005（HTTP 4xx）',
          j5.get('code') == 30005 and 400 <= s5 < 500, 'HTTP %s code=%s' % (s5, j5.get('code')))
    check('5', '自荐不产生 referral 行（前后行数不变：%d）' % before,
          referral_count() == before, 'referral 行数=%d' % referral_count())
    check('5', 'A 对自己也没有产生好友关系',
          friend_row(tok_a, id_a) is None and pair_count(id_a, id_a) == 0,
          'pair 行数=%d' % pair_count(id_a, id_a))

    # ── 断言 8：幂等（重复访问/刷新）──────────────────────────────
    head('8')
    n_ref, n_pair = referral_count(), pair_count(id_a, id_b)
    repeat = []
    for i in range(3):
        st_, j_ = api('POST', '/api/v1/friends/invite',
                      {'invite_code': code_a, 'auto_accept': True}, tok_b)
        repeat.append((st_, j_.get('code'), data_of(j_).get('status')))
    print('    同一链接参数再打 3 次：%s' % repeat)
    check('8', '重复调用全部 HTTP 200 / code=0 / status=accepted（不报错）',
          all(x == (200, 0, 'accepted') for x in repeat), '结果=%s' % repeat)
    check('8', '不重复绑定：referral 行数仍为 %d' % n_ref,
          referral_count() == n_ref and referral_count(id_b) == 1,
          'referral 行数=%d' % referral_count())
    check('8', '不重复建关系：social_friend 行数仍为 %d' % n_pair,
          pair_count(id_a, id_b) == n_pair, '行数=%d' % pair_count(id_a, id_b))
    urls = {invite_url_of(tok_a) for _ in range(3)}
    check('8', '反复 GET /me/referral 返回稳定且不产生新行',
          urls == {url_a} and referral_count() == n_ref, 'urls=%s' % urls)

    # ── 补充 A：改昵称 → nickname / share_text 立刻生效 ───────────
    head('A')
    sA, jA = api('POST', '/api/v1/me/nickname', {'nickname': '晨光小友'}, tok_a)
    print('    改昵称 → HTTP %s code=%s data=%s' % (sA, jA.get('code'),
                                                    json.dumps(data_of(jA), ensure_ascii=False)))
    check('A', 'POST /me/nickname 回传新昵称',
          sA == 200 and data_of(jA).get('nickname') == '晨光小友',
          '返回=%s' % data_of(jA).get('nickname'))
    ref_a2 = data_of(api('GET', '/api/v1/me/referral', None, tok_a))
    print('    改后 GET /me/referral: nickname=%s' % ref_a2.get('nickname'))
    print('    改后 share_text=%s' % ref_a2.get('share_text'))
    check('A', 'GET /me/referral 的 nickname 立刻是新昵称',
          ref_a2.get('nickname') == '晨光小友', 'nickname=%s' % ref_a2.get('nickname'))
    check('A', 'share_text 含新昵称 + 含邀请链接（逐字含 invite_url）',
          '晨光小友' in (ref_a2.get('share_text') or '')
          and url_a in (ref_a2.get('share_text') or '')
          and '?invite=' in (ref_a2.get('share_text') or ''),
          'share_text=%s' % ref_a2.get('share_text'))
    ra2 = friend_row(tok_b, id_a)
    check('A', 'B 的 GET /friends 里 A 的昵称也同步为新值',
          (ra2 or {}).get('nickname') == '晨光小友', 'nickname=%s' % (ra2 or {}).get('nickname'))
    sA2, jA2 = api('POST', '/api/v1/me/nickname', {'nickname': '短'}, tok_a)
    check('A', '越界（1 字）仍返回既有 10002（HTTP 400）',
          sA2 == 400 and jA2.get('code') == 10002, 'HTTP %s code=%s' % (sA2, jA2.get('code')))
    check('A', '越界时昵称不被改动（仍是「晨光小友」）',
          data_of(api('GET', '/api/v1/me/referral', None, tok_a)).get('nickname') == '晨光小友',
          'nickname=%s' % data_of(api('GET', '/api/v1/me/referral', None, tok_a)).get('nickname'))

    # ── 补充 B：免鉴权邀请预览（只回昵称）─────────────────────────
    head('B')
    sB, jB = preview(code_a)                                              # ★ 不带头 = 免鉴权
    dB = data_of(jB)
    print('    无 Authorization 调 preview → HTTP %s code=%s data=%s'
          % (sB, jB.get('code'), json.dumps(dB, ensure_ascii=False)))
    check('B', '免鉴权可访问（HTTP 200 / code=0，不是 401）',
          sB == 200 and jB.get('code') == 0, 'HTTP %s code=%s' % (sB, jB.get('code')))
    check('B', '有效码 → valid=true 且 nickname 是邀请人当前昵称',
          dB.get('valid') is True and dB.get('nickname') == '晨光小友',
          'valid=%s nickname=%s' % (dB.get('valid'), dB.get('nickname')))
    check('B', '响应体**只有** valid / nickname 两个字段（字段级断言）',
          set(dB.keys()) == {'valid', 'nickname'}, '字段=%s' % sorted(dB.keys()))
    check('B', '响应体里不含 member_id（整包文本级断言）',
          'member_id' not in json.dumps(jB, ensure_ascii=False)
          and short(id_a) not in json.dumps(jB, ensure_ascii=False),
          'payload=%s' % json.dumps(jB, ensure_ascii=False))
    sB2, jB2 = preview('ZZZZZZZZ')
    dB2 = data_of(jB2)
    print('    无效码 → HTTP %s code=%s data=%s' % (sB2, jB2.get('code'),
                                                    json.dumps(dB2, ensure_ascii=False)))
    check('B', '无效码 → {valid:false, nickname:null} 且 HTTP 200（不抛错）',
          sB2 == 200 and jB2.get('code') == 0 and dB2.get('valid') is False
          and dB2.get('nickname') is None,
          'HTTP %s data=%s' % (sB2, json.dumps(dB2, ensure_ascii=False)))
    sB3, jB3 = preview('abc')
    check('B', '格式不合法的码同样 valid:false 且 200（前端不用处理异常分支）',
          sB3 == 200 and data_of(jB3).get('valid') is False, 'HTTP %s data=%s'
          % (sB3, json.dumps(data_of(jB3), ensure_ascii=False)))
    sB4, jB4 = preview(None)
    check('B', '缺参数同样 valid:false 且 200', sB4 == 200 and data_of(jB4).get('valid') is False,
          'HTTP %s data=%s' % (sB4, json.dumps(data_of(jB4), ensure_ascii=False)))
    check('B', '改昵称后 preview 也立刻返回新昵称（现读 social_profile）',
          dB.get('nickname') == '晨光小友', 'nickname=%s' % dB.get('nickname'))

    # ── 补充 V：不传 auto_accept 时 v3 原路径不变 ─────────────────
    head('V')
    tok_d, id_d, sd = login('d')
    sV, jV = api('POST', '/api/v1/friends/invite', {'invite_code': code_a}, tok_d)
    print('    D 不传 auto_accept 用 A 的码 → HTTP %s code=%s data=%s'
          % (sV, jV.get('code'), json.dumps(data_of(jV), ensure_ascii=False)))
    check('V', '仍是 pending（未跳过对方确认）',
          sV == 200 and data_of(jV).get('status') == 'pending',
          'status=%s' % data_of(jV).get('status'))
    sV2, jV2 = api('POST', '/api/v1/friends/accept', {'friend_id': id_d}, tok_a)
    check('V', 'A accept 后双方 accepted（既有流程照旧）',
          sV2 == 200 and jV2.get('code') == 0
          and (friend_row(tok_d, id_a) or {}).get('status') == 'accepted',
          'D→A=%s' % (friend_row(tok_d, id_a) or {}).get('status'))
    v_rows = [r for r in referral_rows() if r['referee_member_id'] == id_d]
    check('V', '手工输码路径的 referral 也记一行，source=manual',
          len(v_rows) == 1 and v_rows[0]['source'] == 'manual' and v_rows[0]['referrer_member_id'] == id_a,
          'rows=%s' % json.dumps(v_rows, ensure_ascii=False))

    # ── 补充 C：预览限流（放最后：会把同 IP 的桶打空）────────────
    head('C')
    prior = preview_ok_count()
    print('    本节之前已成功 preview %d 次（同一本账，桶容量 60）' % prior)
    burst, t0 = [], time.time()
    for i in range(61):
        sC, jC = preview(code_a)
        burst.append((i + 1, sC, jC.get('code'), jC.get('detail') or {}))
    dt = time.time() - t0
    rejected = [b for b in burst if b[1] != 200]
    print('    连打 61 次（耗时 %.2fs）：本节成功 %d 次；第一次被拒：%s'
          % (dt, 61 - len(rejected), rejected[0] if rejected else None))
    check('C', '全脚本 preview 成功总数恰为 60（与 LIMITS[api_anon]=60 次/60 秒 一致，可复算）',
          preview_ok_count() == 60, '成功总数=%d（本节前 %d + 本节 %d）'
          % (preview_ok_count(), prior, 61 - len(rejected)))
    check('C', '第 61 次调用即被拒（既有 40000 RATE_LIMITED + HTTP 429）',
          bool(rejected) and rejected[0][0] == 61 - prior and rejected[0][1] == 429
          and rejected[0][2] == 40000,
          '第一次被拒=%s' % (rejected[0] if rejected else None,))
    sC2, jC2 = preview('ZZZZZZZZ')
    check('C', '被限流时连无效码也一并挡掉（防枚举，而不是只挡有效码）',
          sC2 == 429 and jC2.get('code') == 40000, 'HTTP %s code=%s' % (sC2, jC2.get('code')))
    check('C', '限流只拒请求、不写库（referral 行数不变）',
          referral_count() == len(referral_rows()), '行数=%d' % referral_count())

    # ── 收尾：打印 referral 表 ────────────────────────────────────
    rows = print_referral_table()
    print('    成员对照：A=…%s  B=…%s  C=…%s  D=…%s'
          % (short(id_a), short(id_b), short(id_c), short(id_d)))
    print('    referral 覆盖：referee=B→referrer=A（link）、referee=D→referrer=A（manual）')


# ══════════════════════════════════════════════════════════════════
def summarize():
    print('\n=== 汇总（#1–#5、#8 为变更单验收项；A/B/C/V 为本次追加项）===')
    per = {}
    for crit, name, ok, detail in RESULTS:
        per.setdefault(crit, []).append((name, ok, detail))
    for crit in CRIT_ORDER:
        rows = per.get(crit) or []
        if not rows:
            continue
        bad = [r for r in rows if not r[1]]
        print('  断言 #%-2s %s —— %s（%d/%d 项通过）'
              % (crit, CRIT_TITLE[crit], 'PASS' if not bad else 'FAIL',
                 len(rows) - len(bad), len(rows)))
        for name, _ok, detail in bad:
            print('      FAIL: %s  %s' % (name, detail))
    failed = [r for r in RESULTS if not r[1]]
    print('\n  合计 %d 项子断言，通过 %d，失败 %d；本脚本范围 %s'
          % (len(RESULTS), len(RESULTS) - len(failed), len(failed),
             '全部通过' if not failed else '存在失败'))
    with open(RESULT_JSON, 'w', encoding='utf-8') as fp:
        json.dump([{'criteria': c, 'name': n, 'ok': o, 'detail': d} for c, n, o, d in RESULTS],
                  fp, ensure_ascii=False, indent=1)
    print('  明细 JSON: %s' % RESULT_JSON)
    sys.exit(0 if not failed else 2)


if __name__ == '__main__':
    main()
