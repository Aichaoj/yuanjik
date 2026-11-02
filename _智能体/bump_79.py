# -*- coding: utf-8 -*-
import re
p = r'shuzi\web\app.js'
s = open(p, encoding='utf-8').read()
s = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '79';", s, count=1)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('WEB_VER now =', re.search(r"var WEB_VER = '(\d+)'", s).group(1))
