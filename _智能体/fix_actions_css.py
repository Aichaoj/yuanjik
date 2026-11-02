# -*- coding: utf-8 -*-
p = r'shuzi\web\style.css'
s = open(p, encoding='utf-8').read()
old = """.body-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.body-actions .btn { margin-top: 0; }
.body-actions #btnBodyInject { flex: 1 1 120px; }"""
new = """.body-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
.body-actions .btn { margin-top: 0; }
.body-actions #btnBodyTurn, .body-actions #btnBodyMute, .body-actions #btnBodyReset { order: 1; }
.body-actions #btnBodyInject { order: 2; grid-column: 1 / -1; }"""
assert s.count(old) == 1
s = s.replace(old, new)

old2 = """.breath-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.breath-actions .btn { margin-top: 0; flex: 1 1 96px; }
.breath-actions select { flex: 1 1 96px; }"""
new2 = """.breath-actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 12px; }
.breath-actions .btn { margin-top: 0; grid-column: 1 / -1; }
.breath-actions select { width: 100%; }"""
assert s.count(old2) == 1
s = s.replace(old2, new2)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('ok')
