# -*- coding: utf-8 -*-
"""经 MinIO（admin 后台令牌）投递只读诊断载荷，并取回结果。

为什么不用 dpaste：agent 取 dpaste 链接返回 HTTP 400（2026-10-24 实测），既有通道是 img.yuanjk.cn。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(os.path.dirname(HERE))
RESTORED = os.path.join(WS, '_归档', '根级脚本_20261024')
sys.path.insert(0, RESTORED)

PS1 = os.path.join(HERE, '_diag_checkin.ps1')
SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
SITE = 'http://jianyi.aliqq.cc/agent86/'
TAG = 'job_shuzi_diag2'


def get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def main():
    raw = open(PS1, 'rb').read()
    bad = [i for i, b in enumerate(raw) if b > 127]
    if bad:
        raise SystemExit('载荷含非 ASCII 字节 %d 处（首处 %d）' % (len(bad), bad[0]))
    print('载荷 ASCII 校验通过：%d 字节' % len(raw), flush=True)

    import _tool_shuzi_pipeline as pl
    # ★ agent 只认 .txt 载荷：直接传 .ps1 会被当成字节串写成 "36 69 114 ..."（2026-10-24 实测）
    txt = os.path.join(HERE, '_diag_checkin_payload.txt')
    with open(txt, 'wb') as f:
        f.write(raw)
    url = pl.upload_artifacts([txt])[txt]
    print('载荷已托管：' + url, flush=True)
    print('投递回执：' + pl.deliver_job(url, TAG), flush=True)

    deadline = time.time() + 420
    while time.time() < deadline:
        time.sleep(10)
        try:
            listing = get(SINK + '?action=list', timeout=25)
        except Exception as e:
            print('  list err ' + str(e)[:60], flush=True)
            continue
        names = sorted(set(re.findall(r'(out_job_shuzi_diag2[^ \t\r\n]*\.txt)', listing)))
        for name in names:
            try:
                body = get(SITE + name, timeout=30)
            except Exception:
                continue
            if 'members_with_checkin_14d' in body:
                print('=== ' + name + ' ===', flush=True)
                print(body, flush=True)
                open(os.path.join(HERE, '_diag_result.txt'), 'w', encoding='utf-8', newline='\n').write(body)
                print('已存 _diag_result.txt', flush=True)
                return 0
            if 'DIAG_DONE' in body or 'PY_MISSING' in body:
                print('=== ' + name + '（无数据）===', flush=True)
                print(body, flush=True)
        print('  等待结果…（已有 %d 个候选）' % len(names), flush=True)
    print('超时', flush=True)
    return 2


if __name__ == '__main__':
    sys.exit(main())
