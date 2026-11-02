# -*- coding: utf-8 -*-
"""v210 patch：H5 调用原生情绪脉冲并上报（幂等，带断言）。"""
import io, re, sys

W = r"D:\Deepseek智能体\AI元健康\shuzi\web"
app = W + r"\app.js"
htm = W + r"\index.html"
ver = W + r"\version.json"


def rd(p):
    return io.open(p, encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)


s = rd(app)
if "flushEmotionPulse" not in s:
    anchor = "  function toggleEmoCare() {"
    assert anchor in s, "toggleEmoCare anchor missing"
    fn = (
        "  /** v210：向原生要一次聚合值并上报；没有原生桥 / 没授权 / 无事件都静默。 */\n"
        "  function flushEmotionPulse() {\n"
        "    var raw = '';\n"
        "    try { if (window.YJK && window.YJK.emotionPulse) { raw = String(window.YJK.emotionPulse() || ''); } } catch (e) { return; }\n"
        "    if (!raw) { return; }\n"
        "    var d = null;\n"
        "    try { d = JSON.parse(raw); } catch (e) { return; }\n"
        "    if (!d || !d.ok) { return; }\n"
        "    apiFetch('/emotion/pulse', {\n"
        "      method: 'POST',\n"
        "      body: { delta_health: d.delta_health, delta_energy: d.delta_energy,\n"
        "              n_events: d.n_events, source_mask: d.source_mask, confidence: d.confidence }\n"
        "    }).then(function () { /* 静默 */ }, function () { /* 静默 */ });\n"
        "  }\n\n"
    )
    s = s.replace(anchor, fn + anchor, 1)

s2 = re.sub(r"(renderEmoCare\(on\);)(\s+)(return on;)", r"\1\2if (on) { flushEmotionPulse(); }\2\3", s, count=1)
assert "flushEmotionPulse();" in s2, "hook not inserted"
s2 = s2.replace("WEB_VER = '209'", "WEB_VER = '210'")
assert "WEB_VER = '210'" in s2
wr(app, s2)

h = rd(htm).replace("?v=20261102b", "?v=20261102c")
wr(htm, h)
assert "?v=20261102c" in h and "?v=20261102b" not in h

j = rd(ver).replace('"web": "209"', '"web": "210"')
wr(ver, j)
assert '"web": "210"' in j
print("PATCH_OK")
