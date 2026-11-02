# -*- coding: utf-8 -*-
# 1) 测试：S4 先开新会话
p = r'shuzi\_verify_v65\test_session_recording.py'
s = open(p, encoding='utf-8').read()
old = """    st, j = api('/vault/session/status', t=a)
    cur = (j.get('data') or {}).get('session_id')
    if cur:
        sid = cur
    total = 0"""
assert s.count(old) == 1
s = s.replace(old, """    # 先开一轮干净的会话（前面的会话在 S3 中已被 start 自动收尾）
    st, j = api('/vault/session/start', 'POST', {}, a)
    sid = (j.get('data') or {}).get('session_id')
    total = 0""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('test patched')

# 2) 前端：手动结束文案改成「本轮结束」
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
old2 = "vsFinish('已手动结束')"
assert a.count(old2) == 1
a = a.replace(old2, "vsFinish('本轮结束')")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app patched')
