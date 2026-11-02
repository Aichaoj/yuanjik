# -*- coding: utf-8 -*-
import json
p = r'shuzi\web\music.json'
d = json.load(open(p, encoding='utf-8'))
d['tracks'] += [
 {"title": "楞严咒（第二段·长）", "subtitle": "宣化上人念诵节选 · CC BY-SA 3.0",
  "file": "music/shurangama-v2-long-ccbysa3.ogg", "license": "CC BY-SA 3.0",
  "source": "https://commons.wikimedia.org/wiki/File:Usnidha_Sitatapatra_dharani,_Siddham_chant_and_Buddhist_Sanskrit_mantra_chant_2_long_version_1075_1210.ogg",
  "author": "Ven. Chan Master Hsuan Hua（剪辑者以 CC BY-SA 3.0 释出）"},
 {"title": "楞严咒（第二段·短）", "subtitle": "宣化上人念诵节选 · CC BY-SA 3.0",
  "file": "music/shurangama-v2-short-ccbysa3.ogg", "license": "CC BY-SA 3.0",
  "source": "https://commons.wikimedia.org/wiki/File:Usnidha_Sitatapatra_dharani,_Siddham_chant_and_Buddhist_Sanskrit_mantra_chant_2_short_version_1075_1110.ogg",
  "author": "Ven. Chan Master Hsuan Hua（剪辑者以 CC BY-SA 3.0 释出）"},
]
open(p, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('tracks =', len(d['tracks']))

n = r'shuzi\web\music\NOTICE.md'
s = open(n, encoding='utf-8').read()
add = """| `shurangama-v2-long-ccbysa3.ogg` | 楞严咒节选·第二段（1075–1210 秒） | Ven. Chan Master Hsuan Hua（剪辑者按 CC BY-SA 3.0 释出） | **CC BY-SA 3.0** | https://commons.wikimedia.org/wiki/File:Usnidha_Sitatapatra_dharani,_Siddham_chant_and_Buddhist_Sanskrit_mantra_chant_2_long_version_1075_1210.ogg |
| `shurangama-v2-short-ccbysa3.ogg` | 楞严咒节选·第二段（1075–1110 秒） | Ven. Chan Master Hsuan Hua（剪辑者按 CC BY-SA 3.0 释出） | **CC BY-SA 3.0** | https://commons.wikimedia.org/wiki/File:Usnidha_Sitatapatra_dharani,_Siddham_chant_and_Buddhist_Sanskrit_mantra_chant_2_short_version_1075_1110.ogg |
"""
lines = s.splitlines()
# 插在表格最后一行之后
idx = max(i for i, l in enumerate(lines) if l.startswith('| `'))
lines.insert(idx + 1, add.rstrip('\n'))
open(n, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
print('notice rows =', sum(1 for l in open(n, encoding='utf-8') if l.startswith('| `')))
