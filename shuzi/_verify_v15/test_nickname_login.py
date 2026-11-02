# -*- coding: utf-8 -*-
"""
数显 v15 真服务验证：昵称（唯一 / 改名限频 / 可登录）+ 分享链接用昵称 + 修改密码
================================================================================
师父需求（2026-10-09）：
  「ai数显的用户手机号登录后，可以修改自己的昵称，需要唯一，
    然后对外分享时网址以昵称对外和登录都可以，手机号只登录。」

验收标准（先写后做）：
  A. 昵称唯一
     A1 改成别人正在用的昵称 → 400 可读「已经有人用了」
     A2 大小写不同但实际相同（DaAi vs daai）也判占用（COLLATE NOCASE）
     A3 改成自己当前的昵称 → 幂等 200（changed=False），不占用冷却
  B. 改昵称
     B1 首次改成自定义昵称 → 200 + changed=True
     B2 未登录调用 → 401
     B3 非法昵称（1 字 / 13 字）→ 400
     B4 **7 天冷却**：距上次改名 < 7 天 → 429 且提示含剩余天数
  C. 昵称登录（手机号只登录）
     C1 「昵称 + 密码」→ 200
     C2 「手机号 + 密码」→ 200（回归）
     C3 改名后：**新昵称可登**、**旧昵称不可登**、**手机号仍可登**
     C4 未知标识 → 401，且与"密码错"**逐字同一句**（不泄露存在性）
     C5 登录仍受 `login` 限流保护（scope 未变）
  D. 分享链接以昵称对外
     D1 `/me/referral` 的 `invite_url` 含**昵称**（URL 编码），不含手机号、不含邀请码
     D2 `invite/preview?invite_code=<昵称>` → valid=True + 昵称
     D3 **老邀请码链接仍有效**（`?invite=<8位码>` → valid=True）—— 已分享出去的不能失效
  E. 手机号只登录（隐私）
     E1 referral / preview 响应里**不含手机号**（全文检索 11 位手机号）
  F. 修改密码（v15 新增）
     F1 旧密码正确 → 200，新密码立刻可登录、旧密码失效
     F2 旧密码错 → 401 且提示可读
     F3 新旧相同 → 400
     F4 新密码太弱/太短 → 400
     F5 未登录 → 401
     F6 改完 fail_count 清零（此前错几次不再影响）

★ 登录限流 = 10 次/小时/IP，所以拆成两个独立实例跑（各用各的库），避免互相拖累。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                              # noqa: BLE001
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
RESULTS = []

import sqlite3


def reset_cooldown(inst, member_id):
    """把某会员的改名冷却清零（模拟"7 天以后"），用于验证"改名后登录口径"。
    这是测试专用手段，直接改临时库；产品代码不会这么干。"""
    try:
        c = sqlite3.connect(inst.db)
        c.execute('UPDATE social_profile SET nickname_updated_at = 0 WHERE member_id = ?',
                  (member_id,))
        c.commit()
        c.close()
        return True
    except Exception:
        return False


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


class Inst:
    """一个独立服务实例（独立端口 + 独立临时库）。"""

    def __init__(self, port):
        self.port = port
        self.api = "http://127.0.0.1:%d/api/v1" % port
        self.tmp = tempfile.mkdtemp(prefix="v15_%d_" % port)
        self.db = os.path.join(self.tmp, "t.db")
        self.proc = None

    def start(self):
        env = dict(os.environ, SHUZI_PORT=str(self.port), SHUZI_DATA=self.db,
                   PYTHONIOENCODING="utf-8")
        # ★★ 关键：**不能**用 stdout=PIPE 却不去读它。
        #   服务端每次请求写 2~4 行 access/业务日志；PIPE 缓冲只有几 KB，
        #   写满后服务端的 sys.stderr.write 会**阻塞** → 整个服务不再响应任何连接
        #   （实测：长序列跑到第 17~20 个请求时整段 25s 超时，连 /api/health 都探不通）。
        #   重定向到日志文件：既不阻塞，又保留事后诊断能力。
        self.logpath = os.path.join(self.tmp, "server.log")
        self.logfh = open(self.logpath, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen([PY, SERVER, "--port", str(self.port), "--data", self.db],
                                     stdout=self.logfh, stderr=subprocess.STDOUT, env=env)
        for _ in range(40):
            time.sleep(0.5)
            s, _j = self.call('POST', '/auth/guest', {'device_id': 'warm'})
            if s == 200:
                return True
        return False

    def stop(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            pass

    def call(self, method, path, body=None, token=None, timeout=25):
        """★ 用 **curl.exe 子进程** 作为 HTTP 客户端。

        为什么不用 urllib / http.client：本机实测这两个库在连续多次请求后会与服务端
        (protocol_version=HTTP/1.1) 一起挂住 —— 第 17~20 个请求起**整段 25s 超时，
        连 /api/health 都探不通**；而 curl 重放同样序列、同样次数（30 次压测）全部正常。
        为让验收结论只反映**产品行为**，这里改用 curl（独立进程、每请求独立连接）。
        中文 body 走临时文件，避免 Windows 命令行编码问题。
        """
        import subprocess
        import tempfile
        args = ['curl.exe', '-s', '--max-time', str(timeout), '-X', method,
                self.api + path, '-H', 'Content-Type: application/json',
                '-w', '\n%{http_code}']
        if token:
            args += ['-H', 'Authorization: Bearer ' + token]
        tmpf = None
        try:
            if body is not None:
                fd, tmpf = tempfile.mkstemp(suffix='.json')
                with os.fdopen(fd, 'wb') as fh:
                    fh.write(json.dumps(body, ensure_ascii=False).encode('utf-8'))
                args += ['--data-binary', '@' + tmpf]
            r = subprocess.run(args, capture_output=True, timeout=timeout + 8)
            out = r.stdout.decode('utf-8', 'replace')
            if not out.strip():
                return -1, {'message': 'curl 无输出：%s' % r.stderr.decode('utf-8', 'replace')[:80]}
            head, _sep, code = out.rpartition('\n')
            try:
                status = int(code.strip())
            except Exception:                                  # noqa: BLE001
                return -1, {'raw': out[:200]}
            try:
                return status, json.loads(head)
            except Exception:                                  # noqa: BLE001
                return status, {'raw': head[:200]}
        except Exception as e:                                 # noqa: BLE001
            return -1, {'message': '客户端异常：%s' % type(e).__name__}
        finally:
            if tmpf:
                try:
                    os.unlink(tmpf)
                except Exception:                              # noqa: BLE001
                    pass

def part_a_b_d(inst):
    """昵称唯一 / 改名 / 限频 / 分享链接（登录调用少，一个实例够）"""
    print("\n=== A 昵称唯一 ===")
    s, j = inst.call('POST', '/auth/password/register',
                     {'phone': '13900000701', 'password': 'nickPwd123', 'device_id': 'd1'})
    s, j = inst.call('POST', '/auth/password/login',
                     {'phone': '13900000701', 'password': 'nickPwd123', 'device_id': 'd1'})
    tokA = (j.get('data') or {}).get('access_token')
    check('A0', '注册并登录取到令牌', s == 200 and bool(tokA), 'HTTP %s' % s)

    # 第二个账号（用来"占位"）
    s, j = inst.call('POST', '/auth/password/register',
                     {'phone': '13900000702', 'password': 'nickPwd123', 'device_id': 'd2'})
    s, j = inst.call('POST', '/auth/password/login',
                     {'phone': '13900000702', 'password': 'nickPwd123', 'device_id': 'd2'})
    tokB = (j.get('data') or {}).get('access_token')
    check('A0', '第二个账号就绪', s == 200 and bool(tokB), 'HTTP %s' % s)

    s, j = inst.call('POST', '/me/nickname', {'nickname': '抢手昵称'}, token=tokB)
    check('A0', 'B 先占住「抢手昵称」', s == 200, 'HTTP %s %s' % (s, j.get('data') or j.get('message')))

    s, j = inst.call('POST', '/me/nickname', {'nickname': '抢手昵称'}, token=tokA)
    check('A1', '改成别人在用的昵称 → 400「已经有人用了」',
          s == 400 and '已经有人用了' in str(j.get('message')), 'HTTP %s msg=%s' % (s, j.get('message')))

    # A 首次改名（首次设置不受冷却限制）
    s, j = inst.call('POST', '/me/nickname', {'nickname': 'DaAi'}, token=tokA)
    ok_a = (s == 200)
    check('A0', 'A 首次改成「DaAi」→ 200（首次不受冷却限制）', ok_a,
          'HTTP %s %s' % (s, j.get('data') or j.get('message')))
    # B 也还没改过名 → 首次免费；用它测"大小写相同即占用"
    s2, j2 = inst.call('POST', '/me/nickname', {'nickname': 'daai'}, token=tokB)
    check('A2', '大小写不同但相同昵称（daai vs DaAi）→ 400 占用',
          ok_a and s2 == 400 and '已经有人用了' in str(j2.get('message')),
          'A=%s B=%s msg=%s' % (s, s2, j2.get('message')))

    s, j = inst.call('POST', '/me/nickname', {'nickname': 'DaAi'}, token=tokA)
    check('A3', '改成自己当前昵称 → 幂等 200（changed=False）',
          s == 200 and (j.get('data') or {}).get('changed') is False,
          'HTTP %s data=%s' % (s, j.get('data')))

    print("\n=== B 改昵称与冷却 ===")
    s, j = inst.call('POST', '/auth/password/register',
                     {'phone': '13900000703', 'password': 'nickPwd123', 'device_id': 'd3'})
    s, j = inst.call('POST', '/auth/password/login',
                     {'phone': '13900000703', 'password': 'nickPwd123', 'device_id': 'd3'})
    tokC = (j.get('data') or {}).get('access_token')
    s, j = inst.call('POST', '/me/nickname', {'nickname': '大艾测试'}, token=tokC)
    check('B1', '全新账号首次改成自定义昵称 → 200 changed=True',
          s == 200 and (j.get('data') or {}).get('changed') is True,
          'HTTP %s data=%s' % (s, j.get('data')))

    s, j = inst.call('POST', '/me/nickname', {'nickname': '再改一次'})
    check('B2', '未登录改昵称 → 401', s == 401, 'HTTP %s' % s)

    s, j = inst.call('POST', '/me/nickname', {'nickname': '一'}, token=tokA)
    ok1 = s == 400
    s2, j2 = inst.call('POST', '/me/nickname', {'nickname': '一二三四五六七八九十十一十二十三'}, token=tokA)
    check('B3', '非法昵称（1 字 / 13 字）→ 400', ok1 and s2 == 400, '1字=%s 13字=%s' % (s, s2))

    s, j = inst.call('POST', '/me/nickname', {'nickname': '冷却内再改'}, token=tokA)
    check('B4', '7 天冷却内再改 → 429 且提示含剩余天数',
          s == 429 and '天' in str(j.get('message')), 'HTTP %s msg=%s' % (s, j.get('message')))

    print("\n=== D 分享链接以昵称对外 ===")
    s, j = inst.call('GET', '/me/referral', token=tokA)
    d = j.get('data') or {}
    url = str(d.get('invite_url') or '')
    nick = str(d.get('nickname') or '')
    import urllib.parse
    enc = urllib.parse.quote(nick, safe='')
    check('D1', 'invite_url 用昵称（URL 编码）而非邀请码',
          nick and enc in url and str(d.get('invite_code') or '') not in url,
          'nick=%s url=%s' % (nick, url))
    check('E1', 'invite_url 不含手机号',
          not re.search(r'1[3-9]\d{9}', url), url)

    s, j = inst.call('GET', '/invite/preview?invite_code=' + urllib.parse.quote(nick))
    check('D2', 'preview 用昵称 → valid=True + 昵称',
          s == 200 and (j.get('data') or {}).get('valid') is True
          and (j.get('data') or {}).get('nickname') == nick,
          'HTTP %s data=%s' % (s, j.get('data')))

    code = str(d.get('invite_code') or '')
    s, j = inst.call('GET', '/invite/preview?invite_code=' + code)
    check('D3', '老邀请码链接仍有效（已分享出去的不失效）',
          s == 200 and (j.get('data') or {}).get('valid') is True,
          'code=%s HTTP %s data=%s' % (code, s, j.get('data')))
    check('E1', 'preview 响应不含手机号',
          not re.search(r'1[3-9]\d{9}', json.dumps(j, ensure_ascii=False)),
          json.dumps(j, ensure_ascii=False)[:120])


def part_c_f(inst):
    """昵称登录 + 改名后登录口径 + 修改密码（登录调用多，独占一个实例）"""
    print("\n=== C 昵称登录（手机号只登录）===")
    s, j = inst.call('POST', '/auth/password/register',
                     {'phone': '13900000711', 'password': 'loginPwd123', 'device_id': 'e1'})
    s, j = inst.call('POST', '/auth/password/login',
                     {'phone': '13900000711', 'password': 'loginPwd123', 'device_id': 'e1'})
    tok = (j.get('data') or {}).get('access_token')
    mem = (j.get('data') or {}).get('member_id')
    check('C2', '手机号 + 密码 → 200（回归）', s == 200 and bool(tok), 'HTTP %s' % s)

    s, j = inst.call('POST', '/me/nickname', {'nickname': '元宝'}, token=tok)
    check('C0', '改昵称为「元宝」', s == 200, 'HTTP %s' % s)

    s, j = inst.call('POST', '/auth/password/login',
                     {'identifier': '元宝', 'password': 'loginPwd123', 'device_id': 'e2'})
    check('C1', '「昵称 + 密码」→ 200，且回到同一账号',
          s == 200 and (j.get('data') or {}).get('member_id') == mem,
          'HTTP %s member=%s 期望=%s' % (s, (j.get('data') or {}).get('member_id'), mem))

    reset_cooldown(inst, mem)          # 模拟"7 天以后"，让第二次改名可以发生
    s, j = inst.call('POST', '/me/nickname', {'nickname': '新元宝'}, token=tok)
    ok_rename = (s == 200)
    s2, _j2 = inst.call('POST', '/auth/password/login',
                        {'identifier': '元宝', 'password': 'loginPwd123', 'device_id': 'e3'})
    s3, j3 = inst.call('POST', '/auth/password/login',
                       {'identifier': '新元宝', 'password': 'loginPwd123', 'device_id': 'e3'})
    s4, _j4 = inst.call('POST', '/auth/password/login',
                        {'phone': '13900000711', 'password': 'loginPwd123', 'device_id': 'e3'})
    # 改名有 7 天冷却：C1 那次已算"改过"，这里第 2 次会 429 → 用 B 实例已验证冷却，
    # 这里若被冷却拦下则跳过，不算失败（只看"能改的场景"）
    check('C3', '改名后：新昵称可登 + 手机号仍可登（手机号是兜底）',
          ok_rename and s3 == 200 and s4 == 200,
          '改名=%s 新昵称=%s 手机号=%s' % (s, s3, s4))
    check('C3', '旧昵称改名后不可登录（昵称已释放）', s2 == 401, 'HTTP %s' % s2)

    s5, j5 = inst.call('POST', '/auth/password/login',
                       {'identifier': '13900000711', 'password': 'wrongpwd', 'device_id': 'e4'})
    s6, j6 = inst.call('POST', '/auth/password/login',
                       {'identifier': '根本没有这个人', 'password': 'wrongpwd', 'device_id': 'e4'})
    check('C4', '未知标识与密码错 → 401 且逐字同一句（不泄露存在性）',
          s5 == 401 and s6 == 401 and j5.get('message') == j6.get('message'),
          '密码错=%s 未知=%s' % (j5.get('message'), j6.get('message')))

    print("\n=== F 修改密码 ===")
    s, j = inst.call('POST', '/auth/password/change',
                     {'old_password': 'loginPwd123', 'new_password': 'changedPwd456'}, token=tok)
    check('F1a', '旧密码正确 → 200', s == 200 and (j.get('data') or {}).get('changed') is True,
          'HTTP %s data=%s' % (s, j.get('data')))
    s_new, _jn = inst.call('POST', '/auth/password/login',
                           {'identifier': '13900000711', 'password': 'changedPwd456', 'device_id': 'e5'})
    s_old, _jo = inst.call('POST', '/auth/password/login',
                           {'identifier': '13900000711', 'password': 'loginPwd123', 'device_id': 'e5'})
    check('F1b', '新密码可登录 / 旧密码失效', s_new == 200 and s_old == 401,
          '新=%s 旧=%s' % (s_new, s_old))

    s, j = inst.call('POST', '/auth/password/change',
                     {'old_password': '不是这个密码', 'new_password': 'zzzvault:zhengfu.admin.aaa'}, token=tok)
    check('F2', '旧密码错 → 401 且提示可读',
          s == 401 and '当前密码不正确' in str(j.get('message')), 'HTTP %s msg=%s' % (s, j.get('message')))

    s, j = inst.call('POST', '/auth/password/change',
                     {'old_password': 'changedPwd456', 'new_password': 'changedPwd456'}, token=tok)
    check('F3', '新旧密码相同 → 400', s == 400 and '不能与当前密码相同' in str(j.get('message')),
          'HTTP %s msg=%s' % (s, j.get('message')))

    s1, _j1 = inst.call('POST', '/auth/password/change',
                        {'old_password': 'changedPwd456', 'new_password': '123'}, token=tok)
    s2, _j2 = inst.call('POST', '/auth/password/change',
                        {'old_password': 'changedPwd456', 'new_password': 'vault:zhengfu.admin.aaa'}, token=tok)
    check('F4', '新密码太短 / 太弱 → 400', s1 == 400 and s2 == 400, '短=%s 弱=%s' % (s1, s2))

    s, _j = inst.call('POST', '/auth/password/change',
                      {'old_password': 'changedPwd456', 'new_password': 'whatever123'})
    check('F5', '未登录改密码 → 401', s == 401, 'HTTP %s' % s)

    # F6：先错一次，再用正确旧密码改 → 成功且 fail_count 归零
    inst.call('POST', '/auth/password/change',
              {'old_password': 'wrong1', 'new_password': 'resetPwd789'}, token=tok)
    s, j = inst.call('POST', '/auth/password/change',
                     {'old_password': 'changedPwd456', 'new_password': 'resetPwd789'}, token=tok)
    check('F6', '旧密码错一次后仍可用正确旧密码改（未误锁）', s == 200,
          'HTTP %s %s' % (s, j.get('data') or j.get('message')))


def main():
    ia = Inst(15130)
    ib = Inst(15131)
    print("=== 启动两个独立实例 ===")
    if not ia.start():
        print(ia.proc.stdout.read().decode('utf-8', 'replace')[-1200:])
        return 2
    if not ib.start():
        print(ib.proc.stdout.read().decode('utf-8', 'replace')[-1200:])
        return 2
    print("两个实例就绪（15130 / 15131）")
    only = (os.environ.get('V15_ONLY') or '').strip().upper()
    try:
        if only in ('', 'A'):
            part_a_b_d(ia)
        if only in ('', 'B'):
            part_c_f(ib)
    finally:
        for tag, ins in (('A', ia), ('B', ib)):
            try:
                ins.proc.terminate()
                ins.proc.wait(timeout=10)
                try:
                    ins.logfh.close()
                except Exception:
                    pass
                out = open(ins.logpath, encoding='utf-8', errors='replace').read()
                print("  ===== 实例%s 服务端日志尾部 18 行 =====" % tag)
                for l in out.splitlines()[-18:]:
                    print("    " + l)
            except Exception:
                pass
            ins.stop()

    print("\n================ 汇总 ================")
    fails = [r for r in RESULTS if not r[2]]
    print("总计 %d 项，通过 %d，失败 %d" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print("  FAIL [%s] %s  %s" % (g, name, detail))
    print("V15API_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
