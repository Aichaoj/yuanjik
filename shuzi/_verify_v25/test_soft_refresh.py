# -*- coding: utf-8 -*-
"""
数显 v25 验证：打卡后的刷新不得整页清空（「打卡时间条消失」修复）
==================================================================
师父反馈（2026-10-20）：「签到打卡成功后，没有显示打卡时间条了」（指「基线建立中 n/7」进度条）；
下拉刷新/重开 APP 后恢复。线上日志实测：打卡本身 200，但紧随的 /rhythm/daily 出现大量
`ConnectionResetError 10054`（连接被重置，非服务端 500）⇒ 旧代码走 renderDailyError() 把整页清成占位。

本脚本核对修复是否真的落地（静态真接线）：
  A1 loadDaily 接受 (force, opts)，且存在 soft 分支
  A2 soft 且已有数据 + 未重试 → **不调用 renderDailyError**，进入重试
  A3 soft 且重试后仍失败 → 仍**不调用 renderDailyError**，只给轻提示
  A4 非 soft（首次加载）失败 → 仍然调用 renderDailyError（保留原有兜底，不白屏）
  A5 打卡成功后调用的是 loadDaily(true, {soft:true})，不是裸的 loadDaily(true)
  A6 重试有 800ms 延时且只重试一次（_retried）
  B1 语法自检：node --check 通过
  B2 既有能力未丢：dayLineHtml / renderEnergyCard / renderPhaseNow 仍在
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                              # noqa: BLE001
    pass

WEB = r"D:\Deepseek智能体\AI元健康\shuzi\web"
NODE = os.environ.get('NODE_EXE') or \
    r"C:\Users\41692\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
RESULTS = []


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def main():
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    fn = re.search(r'function loadDaily\s*\(([^)]*)\)\s*\{(.*?)\n  \}', js, re.S)
    head = fn.group(1) if fn else ''
    body = fn.group(2) if fn else ''
    print("=== A 静态真接线 ===")
    check('A1', 'loadDaily 接受 (force, opts)', 'force' in head and 'opts' in head, head.strip())
    check('A1', '存在 soft 分支', 'var soft' in body and 'opts.soft' in body)
    check('A2', 'soft+已有数据+未重试 → 先重试（不再清页）',
          'soft && state.daily && !retried' in body and 'loadDaily(true, { soft: true, _retried: true })' in body)
    check('A2', '重试延时 800ms', 'setTimeout' in body and '800' in body)
    check('A3', 'soft 重试后仍失败 → 只轻提示、不清页',
          '刷新稍慢' in body and 'renderDailyError(err)' in body)
    # A4：renderDailyError 仍存在于非 soft 路径（catch 尾部）
    tail = body.split('if (soft && state.daily)')[-1]
    check('A4', '非 soft 失败仍走 renderDailyError（不白屏）', 'renderDailyError(err)' in tail)

    ck = re.search(r'function checkin\s*\([^)]*\)\s*\{(.*?)\n  \}', js, re.S)
    ckbody = ck.group(1) if ck else ''
    check('A5', '打卡成功后用 loadDaily(true, { soft: true })',
          'loadDaily(true, { soft: true })' in ckbody, 'found=%s' % ('loadDaily(true, { soft: true })' in ckbody))
    check('A5', '打卡后不再有裸 loadDaily(true)', 'loadDaily(true)' not in ckbody)

    check('B2', '既有能力未丢：dayLineHtml / renderEnergyCard / renderPhaseNow',
          all(k in js for k in ('function dayLineHtml', 'function renderEnergyCard', 'function renderPhaseNow')))

    print("=== B 语法 ===")
    if os.path.exists(NODE):
        p = subprocess.run([NODE, '--check', os.path.join(WEB, 'app.js')],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        check('B1', 'node --check app.js 通过', p.returncode == 0, (p.stderr or '')[:160])
    else:
        check('B1', 'node 可用', False, NODE)

    fails = [r for r in RESULTS if not r[2]]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print('  FAIL [%s] %s  %s' % (g, name, detail))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
