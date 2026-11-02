# -*- coding: utf-8 -*-
"""由 v61 执行器生成 v62 执行器（文件清单换成 7 件）。"""
src = r'_智能体\deploy\_tool_v61_run.py'
s = open(src, encoding='utf-8').read()
s = s.replace('v61', 'v62').replace('V61', 'V62')
old_files = '''FILES = [
    ("web/index.html", os.path.join(R, r"web\\index.html"), "H_INDEX"),
    ("web/app.js", os.path.join(R, r"web\\app.js"), "H_APPJS"),
    ("web/style.css", os.path.join(R, r"web\\style.css"), "H_CSS"),
    ("web/version.json", os.path.join(R, r"web\\version.json"), "H_VER"),
    ("server/serve.py", os.path.join(R, r"server\\serve.py"), "H_SERVE"),
]'''
new_files = '''FILES = [
    ("web/index.html", os.path.join(R, r"web\\index.html"), "H_INDEX"),
    ("web/app.js", os.path.join(R, r"web\\app.js"), "H_APPJS"),
    ("web/style.css", os.path.join(R, r"web\\style.css"), "H_CSS"),
    ("web/version.json", os.path.join(R, r"web\\version.json"), "H_VER"),
    ("web/music.js", os.path.join(R, r"web\\music.js"), "H_MJS"),
    ("web/music.json", os.path.join(R, r"web\\music.json"), "H_MJSON"),
    ("server/serve.py", os.path.join(R, r"server\\serve.py"), "H_SERVE"),
]'''
assert s.count(old_files) == 1, s.count(old_files)
s = s.replace(old_files, new_files)
open(r'_智能体\deploy\_tool_v62_run.py', 'w', encoding='utf-8', newline='\n').write(s)
print('v62 runner written; FILES lines =', s.count('web/music.js'))
