# -*- coding: utf-8 -*-
"""验证 v99：补充能量行 + 会话卡默认隐藏"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def g(p):
    r = urllib.request.Request(B + p)
    r.add_header('User-Agent', 'Mozilla/5.0')
    return urllib.request.urlopen(r, timeout=20).read().decode('utf-8', 'replace')


h = g('/')
v = json.loads(g('/version.json')).get('web')
print('  [%s] G1 版本 %s' % ('PASS' if v == '99' else 'FAIL', v))
print('  [%s] G2 补充能量行含舒缓不适' %
      ('PASS' if ('btnCComfort' in h and '舒缓不适（意念痛处）' in h) else 'FAIL'))
print('  [%s] G3 会话卡默认隐藏' %
      ('PASS' if ('id="vsCard" hidden' in h) else 'FAIL'))
