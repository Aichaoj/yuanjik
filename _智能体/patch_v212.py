# -*- coding: utf-8 -*-
"""v212：全局录音进度条（任意页面录音时都可见：时长 + 进度 + 麦克风电平）。"""
import io

W = r"D:\Deepseek智能体\AI元健康\shuzi\web"


def rd(p):
    return io.open(p, encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)


s = rd(W + r"\app.js")
if "gRecStart" not in s:
    code = r'''
  /* ══ v212（2026-11-02 师父令）：全局录音进度条 —— 任何页面录音都看得到 ══ */
  var gRecTimer = null;
  function gRecTick() {
    if (!$('gRecFill')) { return; }
    var ms = vs.recStart ? (Date.now() - vs.recStart) : 0;
    var sec = Math.floor(ms / 1000);
    if ($('gRecSec')) {
      $('gRecSec').textContent = ('0' + Math.floor(sec / 60)).slice(-2) + ':' + ('0' + (sec % 60)).slice(-2);
    }
    $('gRecFill').style.width = (((sec % 60) / 60) * 100).toFixed(1) + '%';
    if (vs.analyser && $('gRecPulse')) {
      var b = new Uint8Array(vs.analyser.fftSize);
      vs.analyser.getByteTimeDomainData(b);
      var acc = 0;
      for (var i = 0; i < b.length; i++) { var v = (b[i] - 128) / 128; acc += v * v; }
      var lv = Math.min(1, Math.sqrt(acc / b.length) * 6);
      $('gRecPulse').style.transform = 'scale(' + (1 + lv * 0.7).toFixed(2) + ')';
    }
  }
  function gRecStart() {
    if (!$('gRec')) { return; }
    $('gRec').hidden = false;
    gRecTick();
    if (gRecTimer) { clearInterval(gRecTimer); }
    gRecTimer = setInterval(gRecTick, 200);
  }
  function gRecStop() {
    if (gRecTimer) { clearInterval(gRecTimer); gRecTimer = null; }
    if ($('gRec')) { $('gRec').hidden = true; }
  }
'''
    anchor = "  var vs = { paused: false"
    assert anchor in s, "vs anchor missing"
    s = s.replace(anchor, code + "\n" + anchor, 1)

s = s.replace("        vs.recorder.start(1000);          // 每秒一片，内存占用平稳",
              "        vs.recorder.start(1000);          // 每秒一片，内存占用平稳\n        gRecStart();                       // v212：全局录音进度条")
s = s.replace("    vs.paused = false;\n    if ($('btnVsStart')) { $('btnVsStart').hidden = false; }",
              "    vs.paused = false;\n    gRecStop();                          // v212：录音结束收起进度条\n    if ($('btnVsStart')) { $('btnVsStart').hidden = false; }")
s = s.replace("WEB_VER = '211'", "WEB_VER = '212'")
wr(W + r"\app.js", s)

h = rd(W + r"\index.html")
if 'id="gRec"' not in h:
    h = h.replace("</body>", """<div id="gRec" hidden>
  <span class="grec-dot" id="gRecPulse" aria-hidden="true"></span>
  <span class="grec-txt">录音中</span>
  <span class="grec-time" id="gRecSec">00:00</span>
  <i class="grec-track" aria-hidden="true"><i class="grec-fill" id="gRecFill"></i></i>
</div>
</body>""", 1)
h = h.replace("?v=20261102d", "?v=20261102e")
wr(W + r"\index.html", h)

c = rd(W + r"\style.css")
if "#gRec" not in c:
    c += """
/* v212 全局录音进度条 */
#gRec{position:fixed;left:0;right:0;top:0;z-index:210;display:flex;align-items:center;gap:8px;
  padding:6px 12px;background:rgba(255,255,255,.92);backdrop-filter:blur(6px);
  border-bottom:1px solid #f0dfe4;font-size:12px;color:#8a4a58}
#gRec[hidden]{display:none}
.grec-dot{width:10px;height:10px;border-radius:50%;background:#e04b63;box-shadow:0 0 0 3px rgba(224,75,99,.18);transition:transform .12s}
.grec-time{font-variant-numeric:tabular-nums;color:#c0304a;font-weight:600}
.grec-track{flex:1;height:4px;border-radius:2px;background:#f3e3e7;overflow:hidden}
.grec-fill{display:block;height:100%;width:0;background:linear-gradient(90deg,#ef7f95,#d93a57);transition:width .2s linear}
"""
    wr(W + r"\style.css", c)
print("PATCH_OK")
