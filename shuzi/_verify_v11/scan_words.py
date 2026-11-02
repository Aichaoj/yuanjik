# -*- coding: utf-8 -*-
"""
v11 用词纪律扫描（**独立命令**，交付前手动复扫一遍即可）
=========================================================
扫描对象 = 本次**新增 / 改动**的全部文件 + 运行期产物；命中数必须为 0。

词表**唯一来源**是 `test_family.py` 的 `BANNED_WORDS`（用码点拼装，本脚本与那个文件都不打印词面，
避免"扫描输出文件本身把词面写进磁盘、下一次扫描又命中自己"的自指陷阱）。

用法：
    D:\\Deepseek智能体\\AI元健康\\shuzi\\runtime\\python.exe D:\\Deepseek智能体\\AI元健康\\shuzi\\_verify_v11\\scan_words.py
    …\\scan_words.py  <任意文件或目录> …      # 也可指定扫描目标
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                       # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_family as T                                                 # noqa: E402

# 本次变更涉及的文件（新增 2 个 + 改动 1 个后端 + 改动 3 个前端）
DEFAULT_TARGETS = [
    os.path.join(ROOT, 'server', 'family.py'),
    os.path.join(ROOT, 'server', 'serve.py'),
    os.path.join(ROOT, 'web', 'index.html'),
    os.path.join(ROOT, 'web', 'app.js'),
    os.path.join(ROOT, 'web', 'style.css'),
    os.path.join(HERE, 'test_family.py'),
    os.path.join(HERE, 'browser_family.py'),
    os.path.join(HERE, 'scan_words.py'),
    os.path.join(HERE, 'test_family_result.json'),
    os.path.join(HERE, 'browser_family_result.json'),
    os.path.join(HERE, 'test_family_output.txt'),
]
TEXT_EXT = ('.py', '.js', '.css', '.html', '.json', '.txt', '.md')


def targets():
    if len(sys.argv) > 1:
        out = []
        for arg in sys.argv[1:]:
            if os.path.isdir(arg):
                for base, _dirs, files in os.walk(arg):
                    out += [os.path.join(base, f) for f in files
                            if f.lower().endswith(TEXT_EXT)]
            else:
                out.append(arg)
        return sorted(out)
    return DEFAULT_TARGETS


def main() -> int:
    print('=== v11 用词纪律扫描（词表 %d 条；本脚本不打印词面）===' % len(T.BANNED_WORDS))
    total = 0
    scanned = 0
    for path in targets():
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as fp:
                text = fp.read()
        except OSError as ex:
            print('  %-40s 跳过（%s）' % (os.path.basename(path), type(ex).__name__))
            continue
        scanned += 1
        low = text.lower()
        hits = [i for i, w in enumerate(T.BANNED_WORDS) if w.lower() in low]
        total += len(hits)
        print('  %-40s 字节=%-9d 命中=%d %s'
              % (os.path.basename(path), len(text.encode('utf-8')), len(hits),
                 ('词表下标=%s' % hits) if hits else ''))
    print('=== 扫描 %d 个文件 → 命中合计 = %d（要求 0）===' % (scanned, total))
    return 0 if total == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
