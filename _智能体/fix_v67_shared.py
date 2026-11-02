# -*- coding: utf-8 -*-
p = r'shuzi\web\app.js'
s = open(p, encoding='utf-8').read()
old = "    // v67：我的能量 + 今日可用次数"
assert s.count(old) == 1
s = s.replace(old, """    if ($('vsShared')) { $('vsShared').textContent = vaultFmt((d.shared || {}).index || 0); }

    // v67：我的能量 + 今日可用次数""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('shared shown')
