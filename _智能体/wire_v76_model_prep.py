# -*- coding: utf-8 -*-
"""v76（B 路线第 1 步）：为 3D 人体模型铺路
1) 曲库分片上传支持模型（.glb/.gltf，≤20 MB，落到 web/models/）
2) 静态路由 /models/ 可访问
3) GLTFLoader 已放进 vendor（本地，不依赖外网）
—— 真正的"换成解剖模型 + 分层"要等模型文件与授权确认后再接（见报告"待办"）。
"""

# 1) musiclib：扩展名白名单 + 目标目录按扩展名判断
M = r'shuzi\server\musiclib.py'
s = open(M, encoding='utf-8').read()
s = s.replace("    OK_EXT = ('.ogg', '.mp3', '.m4a', '.wav', '.aac')",
              "    OK_EXT = ('.ogg', '.mp3', '.m4a', '.wav', '.aac', '.glb', '.gltf')")
old_ext = """        ext = os.path.splitext(name)[1].lower()
        if ext not in self.OK_EXT:
            raise AppError(Err.INVALID_FIELD,
                           message='只支持音频：' + ' / '.join(self.OK_EXT), detail={'field': 'filename'})"""
assert s.count(old_ext) == 1
s = s.replace(old_ext, """        ext = os.path.splitext(name)[1].lower()
        if ext not in self.OK_EXT:
            raise AppError(Err.INVALID_FIELD,
                           message='只支持音频或模型：' + ' / '.join(self.OK_EXT),
                           detail={'field': 'filename'})""")

old_dest = """        dest_dir = os.path.join(self.web_dir, 'music')"""
assert s.count(old_dest) == 1
s = s.replace(old_dest, """        is_model = ext in ('.glb', '.gltf')
        dest_dir = os.path.join(self.web_dir, 'models' if is_model else 'music')""")
s = s.replace("        self.audit(event='music_uploaded', upload=uid, file='music/' + safe, bytes=len(buf))",
              "        rel = ('models/' if is_model else 'music/') + safe\n"
              "        self.audit(event='music_uploaded', upload=uid, file=rel, bytes=len(buf))")
s = s.replace("        return {'file': 'music/' + safe, 'bytes': len(buf), 'sha256': sha,",
              "        return {'file': rel, 'bytes': len(buf), 'sha256': sha,")
s = s.replace("                'note': '已落到 web/music/；把 file 填进曲目即可上架'}",
              "                'note': '已落盘；音频填进曲目即可上架，模型供立体图加载'}")
open(M, 'w', encoding='utf-8', newline='\n').write(s)
print('musiclib models ok')

# 2) serve.py：/models/ 前缀
S = r'shuzi\server\serve.py'
t = open(S, encoding='utf-8').read()
old_pre = "    ('/vendor/', 'vendor', 'application/javascript'),"
assert t.count(old_pre) == 1
t = t.replace(old_pre, old_pre + "\n    ('/models/', 'models', 'model/gltf-binary'),")
open(S, 'w', encoding='utf-8', newline='\n').write(t)
print('serve models prefix ok')

import json
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '76'
d['notes'] = ['为立体图换真人体模型铺路：后台上传支持 .glb/.gltf（≤20MB 分片），新增 /models/ 静态目录，GLTFLoader 已本地化'] + [
    n for n in d['notes'] if '.glb' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
import re
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '76';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('web 76')
