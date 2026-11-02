# -*- coding: utf-8 -*-
p = r'shuzi\server\serve.py'
s = open(p, encoding='utf-8').read()
old = "    '/energy.js':   ('energy.js',  'application/javascript; charset=utf-8'),   # v58 人体选部位/呼吸"
assert s.count(old) == 1
s = s.replace(old, old + "\n    '/body3d.js':   ('body3d.js',  'application/javascript; charset=utf-8'),   # v59 立体人体（懒加载 three.js）")
old2 = "    ('/music/', 'music', 'audio/ogg'),                    # v58 佛音曲目（单段文件名，防穿越同其它前缀）"
assert s.count(old2) == 1
s = s.replace(old2, old2 + "\n    ('/vendor/', 'vendor', 'application/javascript'),       # v59 第三方库（three.js，MIT；只读）")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('routes ok')
