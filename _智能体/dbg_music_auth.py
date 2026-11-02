# -*- coding: utf-8 -*-
p = r'shuzi\server\musiclib.py'
s = open(p, encoding='utf-8').read()
old = """        api = getattr(self, 'admin_api', None)
        if api is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台未启用')
        return api._require_admin(headers)"""
assert s.count(old) == 1
new = """        api = getattr(self, 'admin_api', None)
        if api is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台未启用')
        try:
            return api._require_admin(headers)
        except AppError as ex:
            print('[dbg] music auth fail api_id=%s tokens=%d hdr=%s err=%s'
                  % (id(api), len(getattr(api, '_tokens', {}) or {}),
                     str(headers)[:100], getattr(ex, 'code', '?')), flush=True)
            raise"""
s = s.replace(old, new)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('dbg added')
