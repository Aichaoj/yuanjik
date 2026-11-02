# -*- coding: utf-8 -*-
"""把工作区导出成"干净历史"的 Git 仓，推到 GitHub（排除密钥/资料/数据库/大二进制）。"""
import os, shutil, subprocess, sys

SRC = r"D:\Deepseek智能体\AI元健康"
DST = r"C:\Temp\yjk-gh2"
REMOTE = "https://github.com/Aichaoj/yuanjik.git"
PREFIX = ("shuzi/", "服务端/", "核心/", "变更记录/", "_智能体/", "文件目录.md")
BAD_PARTS = ("/_bak", "_bak-", "/data/", "__pycache__", "/uploads", "/_资料", "/.agent",
             "健康超市网")
BAD_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".mp4", ".apk", ".zip", ".7z",
           ".exe", ".dll", ".pdb", ".pyc", ".db", ".db-shm", ".db-wal")


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


files = run(["git", "ls-files"], SRC).stdout.splitlines()
keep = []
for f in files:
    if not f.startswith(PREFIX):
        continue
    if any(b in f for b in BAD_PARTS):
        continue
    if f.lower().endswith(BAD_EXT):
        continue
    if "证书" in f or "私钥" in f:
        continue
    keep.append(f)

total = sum(os.path.getsize(os.path.join(SRC, f)) for f in keep if os.path.isfile(os.path.join(SRC, f)))
print("kept files=%d  size=%.1f MB" % (len(keep), total / 1048576.0), flush=True)

if os.path.isdir(DST):
    shutil.rmtree(DST, ignore_errors=True)
os.makedirs(DST)
for i, f in enumerate(keep):
    src = os.path.join(SRC, f)
    if not os.path.isfile(src):
        continue
    dst = os.path.join(DST, f)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if i % 500 == 0:
        print("  copied %d" % i, flush=True)

open(os.path.join(DST, ".gitignore"), "w", encoding="utf-8").write(
    ".agent/\n_资料/\n健康超市网/\n*.db\n*.db-shm\n*.db-wal\n__pycache__/\n*.pyc\n")
readme = ("# yuanjk-deploy\n\n元神（AI元健康）部署与源码快照。\n"
          "本仓为**干净导出**：不含私钥、用户数据、资料库与大二进制。\n")
open(os.path.join(DST, "README.md"), "w", encoding="utf-8").write(readme)

for cmd in (["git", "init", "-q"], ["git", "checkout", "-q", "-b", "main"],
            ["git", "add", "-A"],
            ["git", "-c", "user.name=yjk-bot", "-c", "user.email=bot@yuanjk.cn",
             "commit", "-q", "-m", "snapshot: v209 source (clean export)"]):
    r = run(cmd, DST)
    if r.returncode != 0:
        print("FAIL", cmd, r.stderr[:300]); sys.exit(3)
print("local commit ok", flush=True)
print(run(["git", "count-objects", "-vH"], DST).stdout.strip(), flush=True)

p = run(["git", "remote", "add", "origin", REMOTE], DST)
print(run(["git", "push", "-u", "origin", "main"], DST).stdout[-2000:], flush=True)
print(run(["git", "push", "-u", "origin", "main"], DST).stderr[-2000:], flush=True)
print("PUSH_EXIT=" + str(run(["git", "ls-remote", "origin"], DST).returncode))
