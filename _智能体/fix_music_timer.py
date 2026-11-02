# -*- coding: utf-8 -*-
p = r'shuzi\web\music.js'
s = open(p, encoding='utf-8').read()
old = """  function play(id) {
    var c = ensureCtx();
    if (!c) { if ($('mpHint')) { $('mpHint').textContent = '这台设备不支持网页音频。'; } return; }
    if (c.state === 'suspended') { c.resume(); }
    stop();"""
assert s.count(old) == 1
new = """  function play(id) {
    var c = ensureCtx();
    if (!c) { if ($('mpHint')) { $('mpHint').textContent = '这台设备不支持网页音频。'; } return; }
    if (c.state === 'suspended') { c.resume(); }
    stop();
    // 定时：默认 5 分钟（"不定时"排在最后，选它才不限时）
    if ($('mpTimer')) { startTimer(Number($('mpTimer').value)); }"""
s = s.replace(old, new)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('default timer applied')
