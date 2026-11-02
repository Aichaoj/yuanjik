# -*- coding: utf-8 -*-
"""v58 服务端静态路由：/energy.js 与 /music/*.ogg"""
P = r'shuzi\server\serve.py'
s = open(P, encoding='utf-8').read()

old = "    '/music.json':  ('music.json', 'application/json; charset=utf-8'),"
assert s.count(old) == 1
s = s.replace(old, old + "\n    '/energy.js':   ('energy.js',  'application/javascript; charset=utf-8'),   # v58 人体选部位/呼吸")

old2 = "STATIC_PREFIXES = (\n    ('/data/', 'data', 'application/octet-stream'),      # 开放数据集（.csv 等）"
assert s.count(old2) == 1
s = s.replace(old2, "STATIC_PREFIXES = (\n    ('/music/', 'music', 'audio/ogg'),                    # v58 佛音曲目（单段文件名，防穿越同其它前缀）\n    ('/data/', 'data', 'application/octet-stream'),      # 开放数据集（.csv 等）")

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('ok:', s.count("'/energy.js'"), s.count("('/music/', 'music'"))
