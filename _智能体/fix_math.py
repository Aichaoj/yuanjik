# -*- coding: utf-8 -*-
p = r'shuzi\server\vault.py'
s = open(p, encoding='utf-8').read()
if '\nimport math\n' not in s:
    s = s.replace('import time\nimport uuid', 'import math\nimport time\nimport uuid', 1)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('math imported:', 'import math' in s)
