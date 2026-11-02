# -*- coding: utf-8 -*-
p = r'shuzi\server\musiclib.py'
s = open(p, encoding='utf-8').read()
old = "rows = self._all('SELECT id, title, subtitle, file, license, author, source FROM music_track'"
assert s.count(old) == 1
s = s.replace(old, "rows = self._rows('SELECT id, title, subtitle, file, license, author, source FROM music_track'")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('fixed _rows')
