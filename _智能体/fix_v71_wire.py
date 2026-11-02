# -*- coding: utf-8 -*-
# 把 vault 的能量接口注入曲库（推荐要用能量指数）
p = r'shuzi\server\serve.py'
s = open(p, encoding='utf-8').read()
old = "        self.vault.admin_api = self.admin"
assert s.count(old) == 1
s = s.replace(old, old + "\n        self.musiclib.energy_api = self.vault      # v71：推荐用能量指数")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print("energy_api wired")
