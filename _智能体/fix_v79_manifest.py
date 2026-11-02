p = r'_智能体\deploy\_tool_v79_run.py'
s = open(p, encoding='utf-8').read()
old = '"web/body3d.js", "server/serve.py", "server/musiclib.py",'
assert s.count(old) == 1
s = s.replace(old, '"web/body3d.js", "web/music.js",\n    "server/serve.py", "server/musiclib.py",')
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('manifest ok:', 'web/music.js' in s)
