# -*- coding: utf-8 -*-
# 1) 后台曲库路由改为 auth_required=False（自带后台令牌校验）
p = r'shuzi\server\musiclib.py'
s = open(p, encoding='utf-8').read()
for name in ('admin_list', 'admin_save', 'admin_toggle', 'admin_delete'):
    old = "        r.route('POST', '/v1/admin/music/save')(self.admin_save)" if name == 'admin_save' else None
s = s.replace("        r.route('GET', '/v1/admin/music')(self.admin_list)",
              "        r.route('GET', '/v1/admin/music', auth_required=False, rate_scope='api')(self.admin_list)")
s = s.replace("        r.route('POST', '/v1/admin/music/save')(self.admin_save)",
              "        r.route('POST', '/v1/admin/music/save', auth_required=False, rate_scope='api')(self.admin_save)")
s = s.replace("        r.route('POST', '/v1/admin/music/toggle')(self.admin_toggle)",
              "        r.route('POST', '/v1/admin/music/toggle', auth_required=False, rate_scope='api')(self.admin_toggle)")
s = s.replace("        r.route('POST', '/v1/admin/music/delete')(self.admin_delete)",
              "        r.route('POST', '/v1/admin/music/delete', auth_required=False, rate_scope='api')(self.admin_delete)")
# 去掉调试
s = s.replace("""        try:
            return api._require_admin(headers)
        except AppError as ex:
            print('[dbg] music auth fail api_id=%s tokens=%d hdr=%s err=%s'
                  % (id(api), len(getattr(api, '_tokens', {}) or {}),
                     str(headers)[:100], getattr(ex, 'code', '?')), flush=True)
            raise""", "        return api._require_admin(headers)")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('musiclib routes fixed; dbg removed')

# 2) 单部位走单音（不经混音），语义更清楚
E = r'shuzi\web\energy.js'
e = open(E, encoding='utf-8').read()
old = """    if (window.YJMusic) {
      if (window.YJMusic.playMix) { window.YJMusic.playMix(yins); }
      else { window.YJMusic.play(primary.yin); }
    }"""
assert e.count(old) == 1
e = e.replace(old, """    if (window.YJMusic) {
      if (yins.length === 1) { window.YJMusic.play(yins[0]); }
      else if (window.YJMusic.playMix) { window.YJMusic.playMix(yins); }
      else { window.YJMusic.play(primary.yin); }
    }""")
open(E, 'w', encoding='utf-8', newline='\n').write(e)
print('energy single-tone ok')
