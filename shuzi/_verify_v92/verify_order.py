# -*- coding: utf-8 -*-
"""验证 v92：贡献面板在共享能量下方、我的能量上方"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def get(p):
    r = urllib.request.Request(B + p)
    r.add_header('User-Agent', 'Mozilla/5.0')
    return urllib.request.urlopen(r, timeout=20).read().decode('utf-8', 'replace')


h = get('/')
v = json.loads(get('/version.json')).get('web')
pos_hero = h.find('vault-hero')
pos_pick = h.find('id="vsPick"')
pos_mine = h.find('id="myEnergyCard"')
print('  [%s] M1 版本 %s' % ('PASS' if v == '92' else 'FAIL', v))
print('  [%s] M2 顺序：共享能量(%d) < 贡献面板(%d) < 我的能量(%d)' %
      ('PASS' if 0 < pos_hero < pos_pick < pos_mine else 'FAIL', pos_hero, pos_pick, pos_mine))
print('  [%s] M3 缓存键已更新' % ('PASS' if '?v=20261027a' in h else 'FAIL'))
