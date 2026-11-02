# -*- coding: utf-8 -*-
"""只读取回：轮询 sink，抓回 job_shuzi_diag 的结果正文（不再投递）。"""
import os
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
SITE = 'http://jianyi.aliqq.cc/agent86/'
HERE = os.path.dirname(os.path.abspath(__file__))


def get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def main():
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            listing = get(SINK + '?action=list', timeout=25)
        except Exception as e:
            print('list err ' + str(e)[:60], flush=True)
            time.sleep(10)
            continue
        names = sorted(set(re.findall(r'(\S*shuzi_diag\S*\.txt)', listing)))
        for name in names:
            try:
                body = get(SITE + name, timeout=30)
            except Exception:
                continue
            if '"members_with_checkin_14d"' in body:
                print('=== ' + name + ' ===', flush=True)
                print(body, flush=True)
                out = os.path.join(HERE, '_diag_result.txt')
                open(out, 'w', encoding='utf-8', newline='\n').write(body)
                print('已存 ' + out, flush=True)
                return 0
        print('waiting… names=' + str(names[-3:]), flush=True)
        time.sleep(12)
    print('timeout', flush=True)
    return 2


if __name__ == '__main__':
    sys.exit(main())
