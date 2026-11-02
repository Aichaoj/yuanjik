# -*- coding: utf-8 -*-
"""
端到端真服务验证 · 轻社交三件套（好友圈 / 健康排行 / 健康互促）
================================================================
对 **打包后的站点树**（`D:\\shuzi\\_dist\\_stage_site`）用**便携运行时**起真服务（端口 15096），
按变更单 §四 的**第 1–10 条**验收标准逐条实测并打印 PASS/FAIL：
  · 第 11 条是前端（另一位同事负责），不在本脚本范围；
  · 第 12 条是既有回归（内核 335 / 服务端 104），由两条 unittest 命令单独跑，本脚本不重复。

运行：
    pwsh -NoProfile -File D:\\shuzi\\build_pack.ps1     # 生成 _stage_site（脚本内也会自动跑一次）
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v3\\test_social.py

第 10 条里「并发创建 50 个邀请码」的说明（如实记录，不回避）：
    契约 §3 的 login 限流是 **10 次/小时/IP**（`app/ratelimit.py` 的 LIMITS，唯一口径源），
    本脚本全程只用 3 个真 HTTP 身份（A/B/C），不去放宽任何限流；
    50 路并发因此走**同一份 `serve.Stack` + 同一份 state.db**（停服后进程内 50 线程，
    真调用 `SocialApi.invite_code()`），并且与 HTTP 阶段已产生的邀请码**一并查重**。
"""
import concurrent.futures as futures
import datetime as _dt
import json
import os
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
HERE = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v3'
PORT = 15096
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, 'social_v3.db')
LOG = os.path.join(HERE, 'test_social.log')
CONC_LOG = os.path.join(HERE, 'test_social_conc_audit.log')
RESULT_JSON = os.path.join(HERE, 'test_social_result.json')
RUN = time.strftime('%m%d%H%M%S')          # 本次运行的设备号后缀，保证每次都是"新用户"

sys.path.insert(0, os.path.join(STAGE, 'server'))
sys.path.insert(0, STAGE)

RESULTS = []          # [(criteria_no, name, ok, detail)]
HTTP_CODES = []       # HTTP 阶段产生的邀请码（供并发阶段合并查重）
CRIT_TITLE = {
    1: '新用户 friends 为空、ranking 不含自己（三开关默认全关）',
    2: 'A 用 B 的邀请码发起 → pending；A 的 feed/ranking 都不含 B',
    3: 'B accept 后双方 GET /friends 互为 accepted',
    4: '双方都开 in_ranking → ranking 含双方且按 score 降序；未开启者不出现',
    5: 'B 开 share_index → A 的 feed 出现分数；关闭后下一次请求即看不到',
    6: 'streak 同理（share_streak 控制）',
    7: '同一好友第 4 次 cheer 被拒（可读业务码 + HTTP 4xx），前 3 次成功',
    8: '全部 cheer 模板通过合规护栏（scan 0 命中）',
    9: 'A DELETE /friends/{B} 后：双方 friends/feed/ranking 均不再出现对方',
    10: '昵称去敏感词；invite_code 8 位且唯一（并发创建 50 个不重复）',
}


def check(crit, name, ok, detail=''):
    ok = bool(ok)
    RESULTS.append((crit, name, ok, str(detail)))
    print('    [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, detail))
    return ok


def head(crit):
    print('\n=== 断言 #%d · %s ===' % (crit, CRIT_TITLE[crit]))


class _Quiet:
    """临时把 stderr 收进文件（服务端审计行不污染断言输出）；同时统计行数。"""

    def __init__(self, path):
        self.path = path
        self.lines = 0
        self._saved = None
        self._fh = None

    def __enter__(self):
        self._saved = sys.stderr
        self._fh = open(self.path, 'w', encoding='utf-8')
        sys.stderr = self._fh
        return self

    def __exit__(self, *_exc):
        sys.stderr = self._saved
        try:
            self._fh.flush()
            with open(self.path, encoding='utf-8', errors='replace') as fp:
                self.lines = sum(1 for _ in fp)
        finally:
            self._fh.close()
        return False


def api(method, path, body=None, token=None, timeout=60):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
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
    """兼容 `api()` 的 (status, json) 与裸 json 两种入参。"""
    if isinstance(payload, tuple):
        payload = payload[1]
    return (payload or {}).get('data') or {}


def login(tag):
    """游客登录（真 HTTP）。返回 (token, member_id)。"""
    s, j = api('POST', '/api/v1/auth/guest', {'device_id': 'v3-%s-%s' % (tag, RUN)})
    d = data_of(j)
    return d.get('access_token', ''), d.get('member_id', ''), s


def friend_row(token, friend_id):
    for f in data_of(api('GET', '/api/v1/friends', None, token)).get('friends') or []:
        if f.get('friend_id') == friend_id:
            return f
    return None


def feed_items(token):
    return data_of(api('GET', '/api/v1/friends/feed', None, token)).get('items') or []


def feed_of(token, friend_id, kind=None):
    return [i for i in feed_items(token)
            if i.get('friend_id') == friend_id and (kind is None or i.get('kind') == kind)]


def rank_items(token):
    return data_of(api('GET', '/api/v1/friends/ranking', None, token)).get('items') or []


def rank_ids(token):
    return [i.get('member_id') for i in rank_items(token)]


def set_privacy(token, **kw):
    s, j = api('POST', '/api/v1/friends/privacy', kw, token)
    return data_of(j)


def get_privacy(token):
    """只读回三开关（前端进入好友圈时先读回，避免把"服务端已关"显示成"已开"）。"""
    return data_of(api('GET', '/api/v1/friends/privacy', None, token))


def birth(token, birth_local, lon, lat):
    return api('POST', '/api/v1/profile/birth',
               {'birth_local': birth_local, 'longitude': lon, 'latitude': lat}, token)


def daily_score(token):
    return (data_of(api('GET', '/api/v1/rhythm/daily', None, token)).get('index') or {}).get('score')


def yesterday():
    return (_dt.date.today() - _dt.timedelta(days=1)).isoformat()


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
        run_http_phases()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:                                           # noqa: BLE001
            proc.kill()
        time.sleep(1)
        logf.close()

    run_concurrency_phase()          # 停服后：同一份代码 + 同一份库，进程内 50 路并发
    summarize()


# ══════════════════════════════════════════════════════════════════
# HTTP 阶段：断言 1–9 + 断言 10 的接口部分
# ══════════════════════════════════════════════════════════════════
def run_http_phases():
    tok_a, id_a, sa = login('a')
    tok_b, id_b, sb = login('b')
    print('    A: HTTP %s member=%s' % (sa, id_a))
    print('    B: HTTP %s member=%s' % (sb, id_b))

    # ── 断言 1 ────────────────────────────────────────────────────
    head(1)
    inv = data_of(api('GET', '/api/v1/me/invite_code', None, tok_a))
    code_a = inv.get('invite_code')
    nick_a = inv.get('nickname')
    print('    A 邀请码=%s 昵称=%s' % (code_a, nick_a))
    check(1, 'invite_code 为 8 位大写字母数字',
          isinstance(code_a, str) and len(code_a) == 8
          and all(c.isdigit() or ('A' <= c <= 'Z') for c in code_a), 'code=%s' % code_a)
    friends = data_of(api('GET', '/api/v1/friends', None, tok_a)).get('friends')
    check(1, 'GET /friends 为空', friends == [], 'friends=%s' % friends)
    ranking = data_of(api('GET', '/api/v1/friends/ranking', None, tok_a))
    check(1, 'ranking 不含自己（items 为空）', ranking.get('items') == [],
          'items=%s' % ranking.get('items'))
    check(1, 'ranking.me.rank 为 null 且未上榜',
          (ranking.get('me') or {}).get('rank') is None
          and (ranking.get('me') or {}).get('on_board') is False,
          'me=%s' % (ranking.get('me') or {}))
    pv = get_privacy(tok_a)                      # GET 只读：前端进好友圈时先读回开关
    check(1, '三开关默认全关（GET /friends/privacy 显式返回 false）',
          pv.get('share_index') is False and pv.get('share_streak') is False
          and pv.get('in_ranking') is False,
          'share_index=%s share_streak=%s in_ranking=%s'
          % (pv.get('share_index'), pv.get('share_streak'), pv.get('in_ranking')))
    pv2 = set_privacy(tok_a)                     # POST 不传任何项 → 逐项保持不变
    check(1, 'POST 未传的项保持不变（仍全关）',
          pv2.get('share_index') is False and pv2.get('share_streak') is False
          and pv2.get('in_ranking') is False, 'POST 后=%s' % pv2)

    # ── 断言 2 ────────────────────────────────────────────────────
    head(2)
    code_b = data_of(api('GET', '/api/v1/me/invite_code', None, tok_b)).get('invite_code')
    s, j = api('POST', '/api/v1/friends/invite', {'invite_code': code_b}, tok_a)
    check(2, 'A 用 B 的邀请码发起 → status=pending',
          s == 200 and j.get('code') == 0 and data_of(j).get('status') == 'pending',
          'HTTP %s status=%s' % (s, data_of(j).get('status')))
    row = friend_row(tok_a, id_b)
    check(2, 'A 的 /friends 中 B 为 pending 且状态字段一律 null',
          bool(row) and row.get('status') == 'pending'
          and row.get('share_index') is None and row.get('score') is None
          and row.get('streak_days') is None and row.get('last_active') is None,
          'row=%s' % row)
    check(2, 'A 的 feed 不含 B', feed_of(tok_a, id_b) == [],
          'feed 中 B 的条目=%s' % feed_of(tok_a, id_b))
    check(2, 'A 的 ranking 不含 B', id_b not in rank_ids(tok_a), 'ranking=%s' % rank_ids(tok_a))
    check(2, 'B 的 feed/ranking 也不含 A',
          feed_of(tok_b, id_a) == [] and id_a not in rank_ids(tok_b),
          'B.feed=%s B.ranking=%s' % (feed_of(tok_b, id_a), rank_ids(tok_b)))

    # ── 断言 3 ────────────────────────────────────────────────────
    head(3)
    s, j = api('POST', '/api/v1/friends/accept', {'friend_id': id_a}, tok_b)
    check(3, 'B accept 成功', s == 200 and j.get('code') == 0,
          'HTTP %s code=%s' % (s, j.get('code')))
    ra, rb = friend_row(tok_a, id_b), friend_row(tok_b, id_a)
    check(3, 'A 侧看 B 为 accepted', bool(ra) and ra.get('status') == 'accepted', 'A→B=%s' % ra)
    check(3, 'B 侧看 A 为 accepted', bool(rb) and rb.get('status') == 'accepted', 'B→A=%s' % rb)

    # ── 建档 + 打卡（让分数与连续天数有真值）──────────────────────
    birth(tok_a, '1990-05-20 08:30', 116.4, 39.9)
    birth(tok_b, '1985-11-03 03:15', 121.5, 31.2)
    api('POST', '/api/v1/checkin', {'on': _dt.date.today().isoformat()}, tok_b)
    api('POST', '/api/v1/checkin', {'on': yesterday()}, tok_b)
    score_b = daily_score(tok_b)
    score_a = daily_score(tok_a)
    print('    B 当日展示分（/v1/rhythm/daily 的 index.score）=%s；A=%s' % (score_b, score_a))

    # C 好友：与 A 已确认，但**不开** in_ranking（用于验证"未开启者不出现"）
    tok_c, id_c, _ = login('c')
    code_c = data_of(api('GET', '/api/v1/me/invite_code', None, tok_c)).get('invite_code')
    api('POST', '/api/v1/friends/invite', {'invite_code': code_c}, tok_a)
    api('POST', '/api/v1/friends/accept', {'friend_id': id_a}, tok_c)
    birth(tok_c, '1993-08-08 22:10', 104.1, 30.7)
    score_c = daily_score(tok_c)
    print('    C=%s（已与 A 确认，但不开 in_ranking），当日分=%s' % (id_c, score_c))

    # ── 断言 4 ────────────────────────────────────────────────────
    head(4)
    set_privacy(tok_a, in_ranking=True)
    set_privacy(tok_b, in_ranking=True)
    set_privacy(tok_c, in_ranking=False)
    items = rank_items(tok_a)
    print('    A 的圈内排行: %s' % json.dumps(
        [{'rank': i['rank'], 'nickname': i['nickname'], 'score': i['score'], 'is_me': i['is_me']}
         for i in items], ensure_ascii=False))
    ids = [i.get('member_id') for i in items]
    check(4, 'ranking 含本人 A 与已开启的 B', id_a in ids and id_b in ids, 'ids=%s' % ids)
    check(4, '未开启 in_ranking 的 C 不出现', id_c not in ids, 'ids=%s' % ids)
    scores = [i.get('score') for i in items if i.get('score') is not None]
    check(4, '按 score 降序', all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
          'scores=%s' % scores)
    # ★ 回归点：A 在**建档之前**就已经访问过 ranking/feed（断言 #1、#2），
    #   若把"无分"也缓存起来，这里就会永远显示 null。分数必须随后续建档正常出现。
    check(4, '先逛好友圈、后建档也能出分（"无分"结果未被缓存）',
          all(i.get('score') is not None for i in items),
          'scores=%s' % [i.get('score') for i in items])
    set_privacy(tok_a, in_ranking=False)
    me = data_of(api('GET', '/api/v1/friends/ranking', None, tok_a)).get('me') or {}
    check(4, '本人关闭后自己不上榜、名次为 null（B 仍在榜）',
          me.get('rank') is None and me.get('on_board') is False and id_a not in rank_ids(tok_a)
          and id_b in rank_ids(tok_a), 'me=%s' % me)
    set_privacy(tok_a, in_ranking=True)          # 复原（后续断言用）

    # ── 断言 5 ────────────────────────────────────────────────────
    head(5)
    set_privacy(tok_b, share_index=True)
    item = (feed_of(tok_a, id_b, 'daily') or [{}])[0]
    print('    B 开 share_index 后，A 的 feed 中 B 条目: score=%s band=%s'
          % (item.get('score'), item.get('score_band')))
    check(5, 'B 开 share_index → A 的 feed 中 B 那条出现分数',
          isinstance(item.get('score'), int) and 0 <= item.get('score') <= 100,
          'score=%s' % item.get('score'))
    check(5, '社交分数与 /v1/rhythm/daily 的 index.score 完全一致（同一公式）',
          item.get('score') == score_b, 'feed=%s daily=%s' % (item.get('score'), score_b))
    set_privacy(tok_b, share_index=False)
    item2 = (feed_of(tok_a, id_b, 'daily') or [{}])[0]
    check(5, 'B 关闭后，下一次请求即看不到分数',
          item2.get('score') is None, '关闭后 score=%s' % item2.get('score'))
    check(5, 'feed 条目带 share_index/share_streak 开关（前端据此显示"未公开"）',
          item.get('share_index') is True and item.get('share_streak') is False
          and item2.get('share_index') is False,
          '开时=%s/%s 关时=%s' % (item.get('share_index'), item.get('share_streak'),
                                  item2.get('share_index')))

    # ── 断言 6 ────────────────────────────────────────────────────
    head(6)
    set_privacy(tok_b, share_streak=True)
    item3 = (feed_of(tok_a, id_b, 'daily') or [{}])[0]
    print('    B 开 share_streak 后，A 的 feed 中 B 条目: streak_days=%s score=%s'
          % (item3.get('streak_days'), item3.get('score')))
    check(6, 'B 开 share_streak → 连续天数出现且为 2（昨+今各一次打卡）',
          item3.get('streak_days') == 2, 'streak_days=%s' % item3.get('streak_days'))
    check(6, 'share_streak 与 share_index 相互独立（此时分数仍不可见）',
          item3.get('score') is None, 'score=%s' % item3.get('score'))
    set_privacy(tok_b, share_streak=False)
    item4 = (feed_of(tok_a, id_b, 'daily') or [{}])[0]
    check(6, 'B 关闭 share_streak 后，下一次请求即看不到连续天数',
          item4.get('streak_days') is None, '关闭后 streak_days=%s' % item4.get('streak_days'))

    # ── 断言 7 ────────────────────────────────────────────────────
    head(7)
    tpls = data_of(api('GET', '/api/v1/friends/cheer/templates', None, tok_a)).get('items') or []
    print('    可用加油模板 %d 条，取第一条用于实测' % len(tpls))
    pre = data_of(api('GET', '/api/v1/friends/cheer/templates', None, tok_a))
    check(7, '加油前额度为 3/3（当日上限 3 次）',
          pre.get('daily_limit') == 3 and pre.get('remaining') == 3
          and pre.get('used_today') == 0,
          'daily_limit=%s remaining=%s' % (pre.get('daily_limit'), pre.get('remaining')))
    tid = tpls[0]['id']
    tries = []
    for i in range(4):
        s, j = api('POST', '/api/v1/friends/cheer',
                   {'friend_id': id_b, 'template_id': tid}, tok_a)
        tries.append((i + 1, s, j.get('code'), j.get('detail') or {}))
    for n, s, code, det in tries:
        print('    第 %d 次 cheer → HTTP %s code=%s %s' % (n, s, code, det if code else ''))
    check(7, '前 3 次成功（HTTP 200 / code=0）',
          all(s == 200 and c == 0 for _n, s, c, _d in tries[:3]),
          '前三次=%s' % [(s, c) for _n, s, c, _d in tries[:3]])
    s4, c4, d4 = tries[3][1], tries[3][2], tries[3][3]
    check(7, '第 4 次被拒：可读业务码 + HTTP 4xx',
          c4 == 40000 and 400 <= s4 < 500,
          'HTTP %s code=%s detail=%s' % (s4, c4, json.dumps(d4, ensure_ascii=False)))
    check(7, '被拒时不落库（当日成功计数仍为 3）',
          d4.get('used_to_friend') == 3 or d4.get('used_total') == 3, 'detail=%s' % d4)

    # ── 断言 8 ────────────────────────────────────────────────────
    head(8)
    from tianyuanheng import guardrail                     # 只读引用合规护栏
    tpl_payload = data_of(api('GET', '/api/v1/friends/cheer/templates', None, tok_a))
    tpls8 = tpl_payload.get('items') or []
    print('    模板 %d 条: %s' % (len(tpls8), [t['text'] for t in tpls8]))
    check(8, '模板 ≥6 条', len(tpls8) >= 6, 'count=%s' % len(tpls8))
    hits_all = {t['id']: guardrail.scan(t['text']) for t in tpls8}
    bad = {k: v for k, v in hits_all.items() if v}
    check(8, '每条模板过护栏 scan() 均 0 命中', not bad,
          '命中=%s' % (bad or '无（0 命中）'))
    check(8, '模板同时给出 id/template_id，且 items 与 templates 两个键同源',
          all(t.get('template_id') == t.get('id') for t in tpls8)
          and len(tpl_payload.get('templates') or []) == len(tpls8)
          and (tpl_payload.get('templates') or [{}])[0].get('text') == tpls8[0]['text'],
          'templates=%d items=%d' % (len(tpl_payload.get('templates') or []), len(tpls8)))
    check(8, '模板接口回传本人当日剩余次数（前端显示"今日还可送 N 次"）',
          tpl_payload.get('daily_limit') == 3 and tpl_payload.get('remaining') == 0
          and tpl_payload.get('used_today') == 3,
          '加油 3 次之后：daily_limit=%s remaining=%s used_today=%s'
          % (tpl_payload.get('daily_limit'), tpl_payload.get('remaining'),
             tpl_payload.get('used_today')))
    # 补充：动态流里真实下发的加油文案也要过护栏
    cheer_texts = [(i.get('cheer') or {}).get('text') for i in feed_of(tok_b, id_a, 'cheer')]
    cheer_texts = [t for t in cheer_texts if t]
    check(8, 'feed 中真实下发的加油文案过护栏 0 命中',
          bool(cheer_texts) and all(not guardrail.scan(t) for t in cheer_texts),
          '文案=%s' % cheer_texts)

    # ── 断言 9 ────────────────────────────────────────────────────
    head(9)
    before = len(feed_of(tok_b, id_a, 'cheer'))
    print('    解除前 B 的 feed 中含 A 的互促条目: %d 条' % before)
    s, j = api('DELETE', '/api/v1/friends/' + id_b, None, tok_a)
    check(9, 'DELETE /api/v1/friends/{B} 返回 removed',
          s == 200 and j.get('code') == 0 and data_of(j).get('removed') is True,
          'HTTP %s data=%s' % (s, json.dumps(data_of(j), ensure_ascii=False)))
    check(9, 'A 的 /friends 不再出现 B', friend_row(tok_a, id_b) is None)
    check(9, 'B 的 /friends 不再出现 A', friend_row(tok_b, id_a) is None)
    check(9, 'A 的 feed 不再出现 B', feed_of(tok_a, id_b) == [],
          'feed=%s' % feed_of(tok_a, id_b))
    check(9, 'B 的 feed 不再出现 A', feed_of(tok_b, id_a) == [],
          'feed=%s' % feed_of(tok_b, id_a))
    check(9, 'A 的 ranking 不再含 B', id_b not in rank_ids(tok_a), 'ranking=%s' % rank_ids(tok_a))
    check(9, 'B 的 ranking 不再含 A', id_a not in rank_ids(tok_b), 'ranking=%s' % rank_ids(tok_b))
    check(9, '往来加油记录一并清除（解除前 %d 条 → 解除后 0 条）' % before,
          before == 3 and feed_of(tok_b, id_a, 'cheer') == [])

    # ── 断言 10（HTTP 部分）───────────────────────────────────────
    head(10)
    # 用护栏词表里的"绝对化用语"类词做输入（与医疗类词走的是同一段清洗逻辑）
    s, j = api('POST', '/api/v1/me/nickname', {'nickname': '全球第一小达人'}, tok_a)
    got = data_of(j).get('nickname')
    check(10, '昵称去敏感词：提交「全球第一小达人」→ 落库昵称已剥离敏感词',
          s == 200 and got == '小达人' and not guardrail.scan(got or ''),
          'HTTP %s 返回=%s' % (s, got))
    s, j = api('POST', '/api/v1/me/nickname', {'nickname': '全球第一'}, tok_a)
    check(10, '清洗后不足以成词的一律拒收（HTTP 400 / code=10002）',
          s == 400 and j.get('code') == 10002,
          'HTTP %s code=%s detail=%s' % (s, j.get('code'),
                                         json.dumps(j.get('detail') or {}, ensure_ascii=False)))
    s, j = api('POST', '/api/v1/me/nickname', {'nickname': '短'}, tok_a)
    check(10, '昵称长度 2-12 字校验（1 字被拒）',
          s == 400 and j.get('code') == 10002, 'HTTP %s code=%s' % (s, j.get('code')))
    codes = [code_a, code_b, code_c]
    check(10, 'HTTP 阶段产生的 3 个邀请码互不相同且格式正确',
          len(set(codes)) == 3 and all(isinstance(c, str) and len(c) == 8 for c in codes),
          'codes=%s' % codes)

    # 断言 9 的补充证据：解除后 A 的 /friends 为空（A 只剩 C，已与 C confirmed）
    leftover = [f.get('friend_id') for f in
                (data_of(api('GET', '/api/v1/friends', None, tok_a)).get('friends') or [])]
    print('    （参考）解除后 A 仍在圈内的好友: %s' % leftover)
    # 记录 HTTP 阶段的邀请码，供并发阶段一并查重
    HTTP_CODES.extend([c for c in codes if c])


# ══════════════════════════════════════════════════════════════════
# 并发阶段：断言 10 的「并发创建 50 个不重复」（同一份代码 + 同一份库）
# ══════════════════════════════════════════════════════════════════
def run_concurrency_phase():
    head(10)
    print('    停服后：同一份 serve.Stack + 同一份 state.db，进程内 50 路并发建档')
    import serve as _serve
    from app.http import RequestContext as _Ctx
    with _Quiet(CONC_LOG) as quiet:              # 把进程内审计行收进文件，保持本输出可读
        stack = _serve.Stack(DB)
        n = 50
        members = []
        for i in range(n):
            dev = 'v3-conc-%s-%02d' % (RUN, i)
            s = stack.auth.login_by_code(code=dev, device_id=dev)
            members.append(s.member_id)
        print('    预建 %d 个会员（member_id 去重后 %d 个）' % (n, len(set(members))))

        def one(mid):
            ctx = _Ctx(trace_id='conc')
            ctx.member_id = mid
            return stack.social.invite_code(ctx=ctx, body={}, headers={})['invite_code']

        t0 = time.time()
        with futures.ThreadPoolExecutor(max_workers=16) as ex:
            codes = list(ex.map(one, members))
        dt = time.time() - t0
        print('    50 路并发完成，耗时 %.2fs；样例: %s' % (dt, codes[:5]))
        check(10, '并发创建的 50 个 invite_code 互不重复',
              len(set(codes)) == n, 'unique=%d/%d' % (len(set(codes)), n))
        check(10, '50 个 invite_code 全部为 8 位大写字母数字',
              all(isinstance(c, str) and len(c) == 8
                  and all(ch.isdigit() or ('A' <= ch <= 'Z') for ch in c) for c in codes),
              '样例=%s' % codes[:3])

        # 同一会员被 50 路并发同时建档 → 必须幂等（只应得到一个码，不产生第二行）
        def same(_i):
            ctx = _Ctx(trace_id='conc-same')
            ctx.member_id = members[0]
            return stack.social.invite_code(ctx=ctx, body={}, headers={})['invite_code']

        with futures.ThreadPoolExecutor(max_workers=16) as ex:
            same_codes = list(ex.map(same, range(50)))
        check(10, '同一会员 50 路并发建档幂等（始终同一个邀请码）',
              len(set(same_codes)) == 1, 'unique=%d' % len(set(same_codes)))
        stack.store.close()
    print('    （本阶段的服务端审计行共 %d 行，已写入 %s）' % (quiet.lines, CONC_LOG))

    allc = list(codes) + list(HTTP_CODES)
    check(10, '与 HTTP 阶段已产生的邀请码合并查重（共 %d 个）' % len(allc),
          len(set(allc)) == len(allc), 'unique=%d/%d' % (len(set(allc)), len(allc)))


# ══════════════════════════════════════════════════════════════════
def summarize():
    print('\n=== 汇总 ===')
    per = {}
    for crit, name, ok, detail in RESULTS:
        per.setdefault(crit, []).append((name, ok, detail))
    for crit in sorted(per):
        rows = per[crit]
        bad = [r for r in rows if not r[1]]
        print('  断言 #%-2d %s  —— %s（%d/%d 项通过）'
              % (crit, CRIT_TITLE[crit], 'PASS' if not bad else 'FAIL',
                 len(rows) - len(bad), len(rows)))
        for name, _ok, detail in bad:
            print('      FAIL: %s  %s' % (name, detail))
    failed = [r for r in RESULTS if not r[1]]
    print('\n  合计 %d 项子断言，通过 %d，失败 %d；断言 #1-#10 %s'
          % (len(RESULTS), len(RESULTS) - len(failed), len(failed),
             '全部通过' if not failed else '存在失败'))
    with open(RESULT_JSON, 'w', encoding='utf-8') as fp:
        json.dump([{'criteria': c, 'name': n, 'ok': o, 'detail': d} for c, n, o, d in RESULTS],
                  fp, ensure_ascii=False, indent=1)
    print('  明细 JSON: %s' % RESULT_JSON)
    sys.exit(0 if not failed else 2)


if __name__ == '__main__':
    main()
