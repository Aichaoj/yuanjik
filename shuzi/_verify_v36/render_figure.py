# -*- coding: utf-8 -*-
"""
v36 图形预览器：把 energy-flow.js 的数字人单独渲染成 PNG，用于「改前 / 改后」对比。
只读 web/ 下文件，只写 _verify_v36\\shots\\。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                    # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
SHOTS = os.path.join(HERE, 'shots')
NODE = r"C:\Users\41692\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"

CASES = [
    ('male_175_70', {'height_cm': 175, 'weight_kg': 70, 'gender': 'male'}),
    ('female_160_52', {'height_cm': 160, 'weight_kg': 52, 'gender': 'female'}),
    ('male_170_95', {'height_cm': 170, 'weight_kg': 95, 'gender': 'male'}),
    ('default_none', None),
]

JS = r"""
const EF = require(%s);
const body = %s;
const idx = {
  score: 72,
  day: {channel: '心'},
  attention: [{channel: '肝'}],
  body: body || undefined,
  channels: [
    {channel:'心', raw: 0.42}, {channel:'肝', raw: -0.51}, {channel:'脾', raw: 0.12},
    {channel:'肺', raw: -0.08}, {channel:'肾', raw: 0.21}, {channel:'胆', raw: -0.19},
    {channel:'胃', raw: 0.09}, {channel:'大肠', raw: -0.05}, {channel:'小肠', raw: 0.11},
    {channel:'膀胱', raw: -0.13}, {channel:'三焦', raw: 0.07}, {channel:'心包', raw: 0.03}
  ]
};
const m = EF.efBuildModel(idx);
process.stdout.write(JSON.stringify({svg: EF.efSvg(m), body: m.body}));
"""


def svg_for(ef_path, body):
    script = JS % (json.dumps(ef_path), json.dumps(body))
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, encoding='utf-8')
    if out.returncode != 0:
        raise SystemExit((out.stderr or '')[:800])
    return json.loads(out.stdout)


def main():
    ef = os.path.join(WEB, 'energy-flow.js').replace('\\', '/')
    os.makedirs(SHOTS, exist_ok=True)
    pages = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={'width': 260, 'height': 540}, device_scale_factor=2)
        for name, body in CASES:
            r = svg_for(ef, body)
            html = ('<html><head><meta charset="utf-8">'
                    '<link rel="stylesheet" href="file:///%s"></head>'
                    '<body style="margin:0;background:#fff">'
                    '<div id="wrap" style="width:240px;height:520px">%s</div>'
                    '</body></html>'
                    % (os.path.join(WEB, 'style.css').replace('\\', '/'), r['svg']))
            f = os.path.join(SHOTS, 'fig_%s.html' % name)
            open(f, 'w', encoding='utf-8').write(html)
            pg.goto('file:///' + f.replace('\\', '/'))
            pg.wait_for_timeout(400)
            png = os.path.join(SHOTS, 'fig_%s.png' % name)
            pg.locator('#wrap').screenshot(path=png)
            pages.append((name, png, r['body']))
            print('%-16s %s  body=%s' % (name, os.path.basename(png), r['body']))
        b.close()


if __name__ == '__main__':
    main()
