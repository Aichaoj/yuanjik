# -*- coding: utf-8 -*-
p = r'shuzi\server\serve.py'
s = open(p, encoding='utf-8').read()

old_imp = "from admin_api import AdminApi, AdminApiDisabled                      # noqa: E402"
assert s.count(old_imp) == 1
s = s.replace(old_imp, old_imp + "\nfrom musiclib import MusicLibApi                                     # noqa: E402  v60 曲库管理")

# 构造放在 records 之后；admin_api 已在前面构造，回填给它做鉴权
old_rec = """        self.records = RecordsApi(self.router, store=self.store,
                                  data_dir=os.path.dirname(os.path.abspath(
                                      data_file or os.environ.get('SHUZI_DATA') or '.')),
                                  audit=_log)"""
assert s.count(old_rec) == 1
new_rec = old_rec + """
        # ★ v60（2026-10-25）：曲库管理。公开列表 /v1/music；后台增删与上下架 /v1/admin/music*。
        #   鉴权复用 admin_api 的令牌（回填句柄，构造顺序不动）。
        self.musiclib = MusicLibApi(self.router, store=self.store, web_dir=WEB_DIR, audit=_log)
        self.musiclib.admin_api = self.admin"""
s = s.replace(old_rec, new_rec)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('serve wired:', s.count('MusicLibApi'))
