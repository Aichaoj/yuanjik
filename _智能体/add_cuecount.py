# -*- coding: utf-8 -*-
p = r'shuzi\web\music.js'
s = open(p, encoding='utf-8').read()
old = "  var cueGain = null;\n  function cue(kind) {"
assert s.count(old) == 1
s = s.replace(old, "  var cueGain = null;\n  var cueCount = 0;\n  function cue(kind) {\n    cueCount++;")
old2 = "    cue: cue,"
assert s.count(old2) == 1
s = s.replace(old2, "    cue: cue,\n    cueCount: function () { return cueCount; },")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('cue counter ok')
