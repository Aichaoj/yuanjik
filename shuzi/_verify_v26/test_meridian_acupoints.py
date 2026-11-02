# -*- coding: utf-8 -*-
"""
数显 v26 验收：经络脉冲 + 五输穴（60 点，点一下才显示名字，青-品红）
=========================================================================
师父令（2026-10-20）：「展现的粒子数字人健康图，增加经络脉冲和穴位」
  选定：B 五输穴 / 点一下才显示名字 / 青-品红。

验收标准（动手前写死）：
  A 静态接线
    A1 energy-flow.js 含 MERIDIANS(12) / FIVE_SHU(12×5) / efAcupoints / efPointAt
    A2 style.css 有经络脉冲（.ef-mer-pulse + @keyframes ef-mer-flow）与穴位样式（.ef-acu / .ef-acu-label）
    A3 index.html 的脚本版本号已更新（缓存击穿）
    A4 尊重 prefers-reduced-motion（脉冲停）
  B 纯函数（Node require）
    B1 十二经各 5 穴 = 60 点；穴名唯一；每经归属正确
    B2 坐标全部落在 viewBox(240×520) 内
    B3 efPointAt(0)/efPointAt(1) 等于起止点；t 单调时弧长单调
    B4 脉冲强度：level = |Δ| / 当日最大，落在 [0,1]；alert 经与节点一致
  C 渲染
    C1 SVG 含 60 个 .ef-acu、60 个 hidden 的 .ef-acu-label（默认不显示名字）
    C2 SVG 含 12 条 .ef-mer-pulse，且 style 里带 --ef-dur/--ef-op（脉冲随读数变）
    C3 viewBox 240×520；粒子仍 5 颗；12 个器官节点仍在
  D 真服务端到端
    D1 真实 index 能生成图；data-acupoints=60；反色节点与 attention 一致
"""
from __future__ import annotations

import json
import os
import re
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
NODE = os.environ.get('NODE_EXE') or \
    r"C:\Users\41692\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
PORT = 15101
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
    print("\n=== A 静态 ===")
    src = open(os.path.join(WEB, 'energy-flow.js'), encoding='utf-8').read()
    css = open(os.path.join(WEB, 'style.css'), encoding='utf-8').read()
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    check('A1', 'energy-flow.js 含 MERIDIANS / FIVE_SHU / efAcupoints / efPointAt',
          all(k in src for k in ('var MERIDIANS', 'var FIVE_SHU', 'function efAcupoints', 'function efPointAt')))
    check('A2', 'style.css 有经络脉冲样式', '.ef-mer-pulse' in css and '@keyframes ef-mer-flow' in css)
    check('A2', 'style.css 有穴位样式', '.ef-acu' in css and '.ef-acu-label' in css)
    m = re.search(r'energy-flow\.js\?v=(\d+)', html)
    check('A3', 'index.html 脚本版本号 >= 20261020', bool(m) and int(m.group(1)) >= 20261020,
          m.group(0) if m else 'NOT FOUND')
    check('A4', 'prefers-reduced-motion 停脉冲', 'prefers-reduced-motion' in css and '.ef-mer-pulse' in css)


def model_checks():
    print("\n=== B 纯函数 ===")
    ef = os.path.join(WEB, 'energy-flow.js').replace('\\', '/')
    idx = {
        'basis': '测试口径', 'day': {'channel': '肝'},
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
const acu = EF.efAcupoints();
const per = {};
acu.forEach(a => { per[a.ch] = (per[a.ch] || 0) + 1; });
const names = acu.map(a => a.name);
const inBox = acu.every(a => a.x >= 0 && a.x <= 240 && a.y >= 0 && a.y <= 520);
const p0 = EF.efPointAt([[0,0],[100,0]], 0);
const p1 = EF.efPointAt([[0,0],[100,0]], 1);
const pm = EF.efPointAt([[0,0],[100,0]], 0.5);
const levels = m.meridians.map(x => x.level);
console.log(JSON.stringify({
  nMer: m.meridians.length,
  nAcu: acu.length,
  perMer: per,
  uniqueNames: new Set(names).size,
  inBox: inBox,
  p0: p0, p1: p1, pm: pm,
  levelsOk: levels.every(v => v >= 0 && v <= 1),
  maxLevelCh: m.meridians.filter(x => x.level === 1).map(x => x.ch),
  alertMers: m.meridians.filter(x => x.alert).map(x => x.ch),
  svgAcu: (svg.match(/class="ef-acu[ "]/g) || []).length,
  svgAcuLabels: (svg.match(/ef-acu-label/g) || []).length,
  svgHidden: (svg.match(/ef-acu-label[^\"]*is-hidden/g) || []).length,
  svgMerPulse: (svg.match(/ef-mer-pulse/g) || []).length,
  svgDur: (svg.match(/--ef-dur:/g) || []).length,
  svgViewBox: svg.indexOf('viewBox="0 0 240 520"') > 0,
  svgParticles: (svg.match(/ef-particle/g) || []).length,
  svgNodes: (svg.match(/class="ef-node[ "]/g) || []).length,
  hasTapBinder: typeof EF.render === 'function'
}));
""" % (ef, json.dumps(idx, ensure_ascii=False))
    out, err = run_node(script)
    if not out:
        check('B0', 'Node 可加载 energy-flow.js', False, (err or '')[:200])
        return
    r = json.loads(out.strip().splitlines()[-1])
    check('B1', '十二经各 5 穴 + 头部 3 穴 = 63 点', r['nAcu'] == 63 and r['nMer'] == 12, 'acu=%s mer=%s' % (r['nAcu'], r['nMer']))
    check('B1', '十二经各 5 穴 + 头部 3 穴',
          all(r['perMer'].get(k) == 5 for k in ('肺','大肠','胃','脾','心','小肠','膀胱','肾','心包','三焦','胆','肝'))
          and r['perMer'].get('头部') == 3, str(r['perMer']))
    check('B1', '63 个穴名互不重复', r['uniqueNames'] == 63, 'unique=%s' % r['uniqueNames'])
    check('B2', '坐标全部落在 240×520 画布内', r['inBox'] is True)
    check('B3', 'efPointAt(0)=起点、efPointAt(1)=终点、中点=50',
          r['p0'] == [0, 0] and r['p1'] == [100, 0] and abs(r['pm'][0] - 50) < 1e-6,
          '%s %s %s' % (r['p0'], r['p1'], r['pm']))
    check('B4', 'level 全在 [0,1]', r['levelsOk'] is True)
    check('B4', '当日最大偏离的经 level=1', '肝' in r['maxLevelCh'], 'max=%s' % r['maxLevelCh'])
    check('B4', 'alert 经与节点反色一致', set(r['alertMers']) <= {'肝', '心'}, 'alert=%s' % r['alertMers'])
    check('C1', 'SVG 含 63 个穴位点（含头部 3 穴）', r['svgAcu'] == 63, 'n=%s' % r['svgAcu'])
    check('C1', '63 个穴名标签默认隐藏', r['svgHidden'] == 63, 'hidden=%s' % r['svgHidden'])
    check('C2', 'SVG 含 12 条经络（左右镜像共 24 段脉冲）', r['svgMerPulse'] == 24, 'n=%s' % r['svgMerPulse'])
    check('C2', '脉冲带 --ef-dur（随读数变化）', r['svgDur'] == 24, 'n=%s' % r['svgDur'])
    check('C3', 'viewBox 240×520、粒子 5、器官节点 12',
          r['svgViewBox'] and r['svgParticles'] >= 5 and r['svgNodes'] == 12,
          'vb=%s p=%s n=%s' % (r['svgViewBox'], r['svgParticles'], r['svgNodes']))



    # v32：能量场光晕——金/粉/灰三层，且随分数变浓变淡
    script2 = """
const EF = require(%r);
const base = {channels:[{channel:'肝',raw:0.2}], attention:[]};
const lo = EF.efSvg(EF.efBuildModel(Object.assign({}, base, {score: 50})));
const hi = EF.efSvg(EF.efBuildModel(Object.assign({}, base, {score: 95})));
const grab = (svg, cls) => { const m = svg.match(new RegExp('ef-aura ' + cls + '\"[^>]*opacity=\"([0-9.]+)')); return m ? Number(m[1]) : -1; };
console.log(JSON.stringify({
  gold: [grab(lo,'ef-aura-gold'), grab(hi,'ef-aura-gold')],
  pink: [grab(lo,'ef-aura-pink'), grab(hi,'ef-aura-pink')],
  grey: [grab(lo,'ef-aura-grey'), grab(hi,'ef-aura-grey')],
  colors: EF.GLOW_LAYERS.every(L => hi.indexOf(L.color) >= 0),
  glowLo: EF.efBuildModel(Object.assign({}, base, {score: 50})).glow,
  glowHi: EF.efBuildModel(Object.assign({}, base, {score: 95})).glow
}));
""" % (ef,)
    out2, err2 = run_node(script2)
    if not out2:
        check('E1', '光晕测试可运行', False, (err2 or '')[:160])
    else:
        r2 = json.loads(out2.strip().splitlines()[-1])
        check('E1', '金/粉/灰三色都在 SVG 里', r2['colors'] is True)
        check('E1', '分数越高光晕越浓（金层）', r2['gold'][1] > r2['gold'][0],
              '%s -> %s' % (r2['gold'][0], r2['gold'][1]))
        check('E1', '分数越高光晕越浓（粉层）', r2['pink'][1] > r2['pink'][0],
              '%s -> %s' % (r2['pink'][0], r2['pink'][1]))
        check('E1', 'glow 随分数单调上升', r2['glowHi'] > r2['glowLo'],
              '%.3f -> %.3f' % (r2['glowLo'], r2['glowHi']))


def live_checks():
    print("\n=== D 真服务端 ===")
    tmp = tempfile.mkdtemp(prefix='v26acu_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    logf = open(log_path, 'wb')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            if call('POST', '/auth/guest', {'device_id': 'warm'})[0] == 200:
                ready = True
                break
        if not ready:
            logf.flush()
            print(open(log_path, encoding='utf-8', errors='replace').read()[-1000:])
            check('D0', '服务就绪', False)
            return
        s, j = call('POST', '/auth/guest', {'device_id': 'v26-acu-dev'})
        tok = ((j.get('data') or {}).get('access_token'))
        call('POST', '/profile/birth',
             {'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT}, token=tok)
        s, j = call('GET', '/rhythm/daily?target_date=2026-10-20', token=tok)
        idx = ((j.get('data') or {}).get('index') or {})
        ef = os.path.join(WEB, 'energy-flow.js').replace('\\', '/')
        script = """
const EF = require(%r);
const idx = %s;
const m = EF.efBuildModel(idx);
const svg = EF.efSvg(m);
const att = (idx.attention||[]).map(a=>a.channel);
console.log(JSON.stringify({n: m.acupoints.length, alerts: m.alerts, att: att,
  acu: (svg.match(/class="ef-acu"/g)||[]).length, mers: m.meridians.length,
  duty: m.nodes.filter(n=>n.onDuty).map(n=>n.ch)}));
""" % (ef, json.dumps(idx, ensure_ascii=False))
        out, err = run_node(script)
        if not out:
            check('D1', '真实 index 可生成图', False, (err or '')[:160])
            return
        r = json.loads(out.strip().splitlines()[-1])
        print('    真实：穴位=%s 经=%s duty=%s alerts=%s' % (r['n'], r['mers'], r['duty'], r['alerts']))
        check('D1', '真实数据仍有 63 穴位 / 12 经', r['n'] == 63 and r['mers'] == 12)
        check('D1', '反色节点 ⊆ attention', set(r['alerts']) <= set(r['att']), '%s vs %s' % (r['alerts'], r['att']))
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
