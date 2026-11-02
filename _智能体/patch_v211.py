# -*- coding: utf-8 -*-
"""v211：情绪快问（早/中/晚）——插 JS、挂启动、绑按钮、升版本。"""
import io, re

W = r"D:\Deepseek智能体\AI元健康\shuzi\web"


def rd(p):
    return io.open(p, encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)


s = rd(W + r"\app.js")
if "maybeAskMood" not in s:
    code = r'''
  /* ══ v211（2026-11-02 师父令）：情绪快问 —— 早/中/晚各问一次，可跳过 ══ */
  var MOOD_SLOTS = [{ k: 'am', from: 6, to: 11 }, { k: 'noon', from: 11, to: 15 },
                    { k: 'pm', from: 17, to: 23 }];
  var MOOD_VAL = { A: 1, B: 0, C: -0.6, D: -1 };
  var MOOD_POS = ['开心', '高兴', '顺利', '成功', '喜欢', '太好了', '好棒', '谢谢', '舒服', '轻松', '幸福', '满意'];
  var MOOD_NEG = ['烦', '生气', '难过', '伤心', '累', '焦虑', '担心', '压力', '委屈', '崩溃', '难受', '痛苦', '吵'];
  var moodPick = '';

  function moodSlotNow() {
    var h = new Date().getHours();
    for (var i = 0; i < MOOD_SLOTS.length; i++) {
      if (h >= MOOD_SLOTS[i].from && h < MOOD_SLOTS[i].to) { return MOOD_SLOTS[i].k; }
    }
    return '';
  }
  function moodDoneKey(slot) { return 'yh.mood.' + ymd() + '.' + slot; }
  function maybeAskMood() {
    if (!getToken()) { return; }
    var slot = moodSlotNow();
    if (!slot || safeGet(moodDoneKey(slot))) { return; }
    state.moodSlot = slot;
    window.setTimeout(function () { if ($('moodAsk')) { openMoodAsk(slot); } }, 4000);
  }
  function openMoodAsk(slot) {
    state.moodSlot = slot; moodPick = '';
    $('moodText').value = '';
    var bs = document.querySelectorAll('#moodAsk .mood-opts button');
    for (var i = 0; i < bs.length; i++) { bs[i].classList.remove('is-on'); }
    $('moodAsk').hidden = false;
  }
  function closeMoodAsk(mark) {
    if (mark && state.moodSlot) { safeSet(moodDoneKey(state.moodSlot), '1'); }
    $('moodAsk').hidden = true;
  }
  function moodTextValence(t) {
    var p = 0, n = 0;
    for (var i = 0; i < MOOD_POS.length; i++) { if (t.indexOf(MOOD_POS[i]) >= 0) { p++; } }
    for (var j = 0; j < MOOD_NEG.length; j++) { if (t.indexOf(MOOD_NEG[j]) >= 0) { n++; } }
    if (p + n === 0) { return 0; }
    return (p - n) / (p + n);
  }
  function submitMood() {
    if (!state.moodSlot) { return; }
    var v = (moodPick && typeof MOOD_VAL[moodPick] === 'number') ? MOOD_VAL[moodPick] : null;
    var t = String($('moodText').value || '').trim();
    if (t) { var tv = moodTextValence(t); v = (v === null ? tv : v + tv); }
    if (v === null) { toast('先选一个，或写一句话。', 'err'); return; }
    v = Math.max(-1, Math.min(1, v));
    closeMoodAsk(true);
    if (Math.abs(v) < 0.25) { toast('收到，保持好心情。', 'ok'); return; }
    var d = Math.min(10, Math.max(1, Math.round(Math.abs(v) * 10)));
    d = v > 0 ? d : -d;
    // 用户亲手作答＝同意用它调整；先确保开关打开，再上报
    apiFetch('/emotion/consent', { method: 'POST', body: { enabled: true } })
      .then(function () {
        return apiFetch('/emotion/pulse', {
          method: 'POST',
          body: { delta_health: d, delta_energy: d, n_events: 1,
                  source_mask: 4, confidence: 0.85 }
        });
      })
      .then(function (env) {
        var r = env.data || {};
        toast(r.accepted ? '收到，元神会留意您的状态。'
                         : '收到，这一小时已经记过了。', 'ok');
      }, function () { toast('已收到，稍后会一起计算。', 'ok'); });
  }
'''
    anchor = "  function toggleEmoCare() {"
    assert anchor in s
    s = s.replace(anchor, code + "\n" + anchor, 1)

# 启动时问一次
if "maybeAskMood();" not in s:
    m = re.search(r"(sessionReady\.then\(function \(\) \{\n)", s)
    assert m, "sessionReady anchor missing"
    s = s[:m.end()] + "        maybeAskMood();\n" + s[m.end():]

s = s.replace("WEB_VER = '210'", "WEB_VER = '211'")
assert "WEB_VER = '211'" in s
wr(W + r"\app.js", s)

h = rd(W + r"\index.html")
if 'id="moodOk"' in h and "getElementById('moodOk')" not in h:
    bind = """
<script>
(function () {
  function bindMood() {
    var box = document.getElementById('moodAsk');
    if (!box) { return; }
    box.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-mood]') : null;
      if (b) {
        var bs = box.querySelectorAll('[data-mood]');
        for (var i = 0; i < bs.length; i++) { bs[i].classList.remove('is-on'); }
        b.classList.add('is-on');
      }
    });
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', bindMood); }
  else { bindMood(); }
})();
</script>
</body>"""
    h = h.replace("</body>", bind, 1)
h = h.replace("?v=20261102c", "?v=20261102d")
wr(W + r"\index.html", h)

v = rd(W + r"\version.json").replace('"web": "210"', '"web": "211"')
wr(W + r"\version.json", v)
print("PATCH_OK")
