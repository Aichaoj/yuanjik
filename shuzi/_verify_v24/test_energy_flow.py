# -*- coding: utf-8 -*-
"""
数显 v24 真服务验证：人类能量粒子流变图（十二通道读数可视化 + 反色差高亮）
=========================================================================
师父令（2026-10-19）：「在数字元神增加人类能量粒子流变图。根据用户健康突出有问题部分的反色差。」

验收标准（动手前写死）：
  A 静态接线
    A1 index.html 有 #energyCard 与 #energyBody，且引入 energy-flow.js（在 app.js 之前）
    A2 app.js 定义 renderEnergyCard，且在 renderIndexCard 的两个分支都被调用
    A3 style.css 有反色样式（.ef-node.is-alert .ef-dot）与光晕脉动（.ef-halo）
  B 纯函数（Node 直接 require energy-flow.js）
    B1 EF_NODES 恰好 12 个，覆盖内核十二通道
    B2 有数据：12 个节点全部 hasValue；alert 集合 ⊆ attention 且非空（示例数据的最大偏离通道必入选）
    B3 onDuty 与 idx.day.channel 一致；无 day 字段时为 false
    B4 空数据：hasData=false、render 返回 false（调用方据此整卡隐藏）
  C 真服务端到端
    C1 /rhythm/daily 的 index.channels 仍 12 条（既有字段未破坏）
    C2 把真实 index 喂给 EF → 生成的 SVG 含 is-alert 的个数 == model.alerts 长度，且含 ef-halo
    C3 反色节点必须带 ef-label-val（显示 Δ），常态节点不带
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                              # noqa: BLE001
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
WEB = os.path.join(ROOT, "web")
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
KERNEL = r"D:\Deepseek智能体\AI元健康\核心"
APP_ROOT = r"D:\Deepseek智能体\AI元健康\服务端"
NODE = os.environ.get('NODE_EXE') or r"C:\Users\41692\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
PORT = 15100
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []
BIRTH = '1985-06-15T14:30'
LON, LAT = 116.4074, 39.9042


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def call(method, path, body=None, token=None, timeout=30):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:                                      # noqa: BLE001
            return e.code, {'raw': raw[:200]}
    except Exception as e:                                     # noqa: BLE001
        return -1, {'message': '客户端异常：%s' % type(e).__name__}


def run_node(script, timeout=60):
    if not os.path.exists(NODE):
        return None, 'node 不存在: ' + NODE
    fd, path = tempfile.mkstemp(suffix='.js')
    os.close(fd)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(script)
        p = subprocess.run([NODE, path], capture_output=True, text=True, timeout=timeout,
                           encoding='utf-8', errors='replace')
        return p.stdout, p.stderr
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def static_checks():
    print("\n=== A 静态接线 ===")
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    css = open(os.path.join(WEB, 'style.css'), encoding='utf-8').read()
    check('A1', 'index.html 有 #energyCard / #energyBody',
          'id="energyCard"' in html and 'id="energyBody"' in html)
    i_ef = html.find('energy-flow.js')
    i_app = html.find('src="app.js"')
    check('A1', 'energy-flow.js 在 app.js 之前引入', i_ef > 0 and i_app > i_ef,
          'ef=%d app=%d' % (i_ef, i_app))
    check('A2', 'app.js 定义 renderEnergyCard', 'function renderEnergyCard' in js)
    body = re.search(r'function renderIndexCard\s*\(d\)\s*\{.*?\n  \}', js, re.S)
    seg = body.group(0) if body else ''
    check('A2', 'renderIndexCard 两个分支都调用 renderEnergyCard',
          seg.count('renderEnergyCard(') >= 2, '调用 %d 次' % seg.count('renderEnergyCard('))
    check('A3', 'style.css 有反色节点样式', '.ef-node.is-alert .ef-dot' in css)
    check('A3', 'style.css 有光晕脉动', '.ef-halo' in css and '@keyframes ef-pulse' in css)
    check('A3', 'style.css 尊重 prefers-reduced-motion', 'prefers-reduced-motion' in css)


def model_checks():
    print("\n=== B 纯函数（Node require）===")
    ef_path = os.path.join(WEB, 'energy-flow.js').replace('\\', '/')
    idx = {
        'basis': '测试口径',
        'day': {'channel': '肝'},
        'channels': [
            {'channel': '肝', 'raw': 0.30, 'direction': '偏亢'},
            {'channel': '心', 'raw': 0.28, 'direction': '偏亢'},
            {'channel': '脾', 'raw': 0.04, 'direction': '平稳'},
            {'channel': '肺', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '肾', 'raw': 0.06, 'direction': '平稳'},
            {'channel': '胆', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '胃', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '大肠', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '小肠', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '膀胱', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '心包', 'raw': 0.05, 'direction': '平稳'},
            {'channel': '三焦', 'raw': 0.05, 'direction': '平稳'}
        ],
        'attention': [{'channel': '肝', 'direction': '偏亢'}, {'channel': '心', 'direction': '偏亢'}]
    }
    script = """
const EF = require(%r);
const idx = %s;
const m = EF.efBuildModel(idx);
const svg = EF.efSvg(m);
const empty = EF.efBuildModel({channels: []});
console.log(JSON.stringify({
  n: EF.EF_NODES.length,
  nodes: m.nodes.length,
  allHaveValue: m.nodes.every(n => n.hasValue),
  alerts: m.alerts,
  duty: m.nodes.filter(n => n.onDuty).map(n => n.ch),
  svgAlerts: (svg.match(/class=\"ef-node[^\"]*is-alert/g) || []).length,
  svgHalos: (svg.match(/ef-halo/g) || []).length,
  svgVals: (svg.match(/ef-label-val/g) || []).length,
  hasViewBox: svg.indexOf('viewBox="0 0 240 520"') > 0,
  hasParticles: (svg.match(/ef-particle/g) || []).length,
  emptyHasData: empty.hasData,
  emptySvg: EF.efSvg(empty),
  renderNoContainer: EF.render(null, idx)
}));
""" % (ef_path, json.dumps(idx, ensure_ascii=False))
    out, err = run_node(script)
    if not out:
        check('B0', 'Node 可 require energy-flow.js', False, (err or '')[:160])
        return
    try:
        r = json.loads(out.strip().splitlines()[-1])
    except Exception as e:                                     # noqa: BLE001
        check('B0', 'Node 输出可解析', False, str(e)[:120] + ' | ' + out[:120])
        return
    check('B1', 'EF_NODES 恰好 12 个', r['n'] == 12, 'n=%s' % r['n'])
    check('B2', '12 个节点全部有读数', r['allHaveValue'] is True)
    check('B2', 'alert 非空且 ⊆ attention', bool(r['alerts']) and set(r['alerts']) <= {'肝', '心'},
          'alerts=%s' % r['alerts'])
    check('B3', 'onDuty 与 idx.day.channel 一致', r['duty'] == ['肝'], 'duty=%s' % r['duty'])
    check('B4', '空数据 → hasData=false', r['emptyHasData'] is False)
    check('B4', '空数据 → SVG 为空串', r['emptySvg'] == '')
    check('B4', 'render(null) 返回 false', r['renderNoContainer'] is False)
    check('C2', 'SVG 含 viewBox 与粒子', r['hasViewBox'] and r['hasParticles'] >= 5,
          'particles=%s' % r['hasParticles'])
    check('C2', 'SVG 中 is-alert 个数 == alerts 长度',
          r['svgAlerts'] == len(r['alerts']), '%s vs %s' % (r['svgAlerts'], len(r['alerts'])))
    check('C2', 'SVG 中 ef-halo 个数 == alerts 长度',
          r['svgHalos'] == len(r['alerts']), '%s vs %s' % (r['svgHalos'], len(r['alerts'])))
    check('C3', '反色节点带 Δ 标注', r['svgVals'] == len(r['alerts']),
          '%s vs %s' % (r['svgVals'], len(r['alerts'])))


def live_checks():
    print("\n=== C 真服务端到端 ===")
    tmp = tempfile.mkdtemp(prefix='v24ef_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    logf = open(log_path, 'wb')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                            env=env)
    try:
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            s, _j = call('POST', '/auth/guest', {'device_id': 'warm'})
            if s == 200:
                ready = True
                break
        if not ready:
            logf.flush()
            print(open(log_path, encoding='utf-8', errors='replace').read()[-1200:])
            check('C0', '服务就绪', False)
            return
        s, j = call('POST', '/auth/guest', {'device_id': 'v24-ef-dev'})
        tok = ((j.get('data') or {}).get('access_token'))
        call('POST', '/profile/birth',
             {'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT}, token=tok)
        s, j = call('GET', '/rhythm/daily?target_date=2026-10-19', token=tok)
        idx = ((j.get('data') or {}).get('index') or {})
        chs = idx.get('channels') or []
        check('C1', 'index.channels 仍 12 条', len(chs) == 12, 'n=%d' % len(chs))

        ef_path = os.path.join(WEB, 'energy-flow.js').replace('\\', '/')
        script = """
const EF = require(%r);
const idx = %s;
const m = EF.efBuildModel(idx);
const svg = EF.efSvg(m);
console.log(JSON.stringify({alerts: m.alerts, att: (idx.attention||[]).map(a=>a.channel),
  svgAlerts: (svg.match(/class=\"ef-node[^\"]*is-alert/g)||[]).length, duty: m.nodes.filter(n=>n.onDuty).map(n=>n.ch)}));
""" % (ef_path, json.dumps(idx, ensure_ascii=False))
        out, err = run_node(script)
        if not out:
            check('C2', '真实 index 可喂给 EF', False, (err or '')[:160])
            return
        r = json.loads(out.strip().splitlines()[-1])
        print('    真实 alerts=%s attention=%s duty=%s' % (r['alerts'], r['att'], r['duty']))
        check('C2', '真实数据能产生反色节点', bool(r['alerts']), 'alerts=%s' % r['alerts'])
        check('C2', 'SVG 反色节点数与模型一致',
              r['svgAlerts'] == len(r['alerts']), '%s vs %s' % (r['svgAlerts'], len(r['alerts'])))
        check('C3', '真实 duty 与 index.day.channel 一致',
              r['duty'] == ([(idx.get('day') or {}).get('channel')] or []),
              'duty=%s' % r['duty'])
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:                                      # noqa: BLE001
            proc.kill()
        logf.close()


def main():
    static_checks()
    model_checks()
    live_checks()
    fails = [r for r in RESULTS if not r[2]]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print('  FAIL [%s] %s  %s' % (g, name, detail))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
