# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v60\test_organ_cue_musiclib.py'
s = open(p, encoding='utf-8').read()
old = "        page.click('#mpStop')\n        page.click('#btnBack')"
new = "        page.evaluate(\"() => window.YJMusic.stop()\")\n        page.click('#btnBack')"
assert s.count(old) == 1
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('patched stop step')
