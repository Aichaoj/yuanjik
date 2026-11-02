# -*- coding: utf-8 -*-
"""v211b：把情绪快问的按钮绑进 bind()（选项 / 告诉元神 / 稍后 / 语音）。"""
import io

P = r"D:\Deepseek智能体\AI元健康\shuzi\web\app.js"
s = io.open(P, encoding="utf-8").read()

anchor = "    if ($('btnEmoCare')) { $('btnEmoCare').addEventListener('click', toggleEmoCare); }"
assert anchor in s, "anchor missing"

block = anchor + """
    // v211：情绪快问按钮
    (function bindMoodAsk() {
      if (!$('moodOk')) { return; }
      $('moodOk').addEventListener('click', submitMood);
      $('moodLater').addEventListener('click', function () { closeMoodAsk(false); });
      $('moodVoice').addEventListener('click', function () {
        try { $('moodText').focus(); } catch (e) { /* 忽略 */ }
        toast('按住麦克风说一句，或直接打字都可以。', 'ok');
      });
      var bs = document.querySelectorAll('#moodAsk [data-mood]');
      for (var i = 0; i < bs.length; i++) {
        bs[i].addEventListener('click', function (e) {
          var b = e.currentTarget;
          var all = document.querySelectorAll('#moodAsk [data-mood]');
          for (var j = 0; j < all.length; j++) { all[j].classList.remove('is-on'); }
          b.classList.add('is-on');
          moodPick = b.getAttribute('data-mood') || '';
        });
      }
    })();"""

s = s.replace(anchor, block, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("BIND_OK")
